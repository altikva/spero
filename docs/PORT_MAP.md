# Spero Phase-1 Port Map

Maps the legacy Python 2 "bot" (`/Users/joy/IdeaProjects/bot/cluster`) onto Spero's
Python 3.12 seams (`providers/`, `probes/`, `remediations/`, `core/`, plus
`store/`, `api/`, `alerting/`, `ai/`). Phase 0 already ported the host command
executor (`connexion.run_command` -> `providers/command.py`).

Disposition legend:
- **PORT** — bring the logic over, modernized (typed, Py3, no global state).
- **REWRITE** — concept is good; reimplement cleanly for async/typing/policy model.
- **DROP** — Orange/Hadoop-specific or obsolete; do not carry over.
- **PLUGIN** — Ambari/Hadoop-specific; goes into an *optional* adapter, not core.

---

## 1. The supervision loop (the heart)

### Legacy algorithm (`supervision.py::perform_oversee`, `node_handler.py`)

For a host, the loop is:

1. Load supervised items from DB: `get_all_components_on_node(host)` returns
   `(others, node_processes, node_services)` plus disks.
2. **Probe** each item:
   - processes -> `Handler.get_one_process_status` -> `get_process_pid(...)`; zero
     pids => fallen.
   - services -> `Handler.get_one_service_status` -> `is_service_running(...)`.
   - disks -> `get_disk_infos` -> megacli `PredictiveFailureCount`/`FirmwareState`.
   Probes run concurrently via `ThreadPoolExecutor` (`get_node_components_status`).
3. **Count failures + alert**: every fallen item calls `save_alerts` ->
   `save_one_alert` (creates `Alert(state='NA')` or increments `count`; emails on
   create). On a *healthy* probe, `acknowledge_alerts` resets `nb_fails = 0` and
   flips the alert to `'A'`. The per-item failure counter is
   `NodeComponent.nb_fails`.
4. **Remediate under threshold**: `handle_restart(items, target)` only acts on
   items whose `nb_fails >= NB_FAILS_BEFORE_AUTO_RESTART` (and only if
   `auto_restart` is set), then fans the restart target out over a pool.
   Remediation is gated globally by `JSON_CC_ACTION_FREEZE` (`msg_action_freeze`)
   and per-item by a "blackout" flag file (`/var/opt/FlagBlackOut/<name>.off`).

So the core cycle is exactly the spec: **probe -> count failures -> remediate
under NB_FAILS_BEFORE_AUTO_RESTART -> alert**, with a global freeze and a
per-target suppression flag.

### Target mapping -> `core/` engine + autonomy

REWRITE this loop as a typed engine (new file `src/spero/core/engine.py`,
ideally async). Per target in the loaded `Policy`:

```
provider = make_provider(target.provider)            # providers/host.py (done)
result   = probe.check(provider)                     # probes/<type>.py
if result.healthy:
    reset failure count; resolve open alert (Event kind="info")
else:
    n = increment failure count for (node, target)
    record Event(kind="probe_fail")
    raise/record Alert if first failure  -> alerting/
    for rem in target.remediations:
        if policy.frozen: skip (record "action freeze")        # == ACTION_FREEZE
        if n < rem.max_attempts: skip (wait/escalate)          # == NB_FAILS_BEFORE_AUTO_RESTART
        if autonomy == suggest: record suggestion, do not act
        if autonomy in (gated, auto): rem.apply(provider)
```

Mapping of legacy concepts to the new model (already half-present in
`core/models.py` and `core/policy.py`):

| Legacy | Target |
|--------|--------|
| `NB_FAILS_BEFORE_AUTO_RESTART` (`config.JSON_CC_NB_FAILS_BEFORE_AUTO_RESTART`) | `RemediationSpec.max_attempts` (already noted in models.py) |
| `JSON_CC_ACTION_FREEZE` global flag | `Policy.frozen` (already present) |
| `NodeComponent.auto_restart` (per-item opt-in) | `RemediationSpec.autonomy` (`suggest` vs `gated`/`auto`) |
| `NodeComponent.nb_fails` / `SupFailureCounter` | engine-held failure counter, persisted as `Event(kind="probe_fail")` rows or a small counters table |
| `/var/opt/FlagBlackOut/<name>.off` blackout file | a per-target "muted/maintenance" state (DB flag), NOT a flag file — REWRITE |
| `ThreadPoolExecutor` fan-out | `asyncio.gather` over targets (or a bounded pool) |
| `AMBARI_NB_FAILS_BEFORE_GRACEFUL_RESTART` (graceful vs hard) | escalation ladder: a second `RemediationSpec` with higher `max_attempts` (e.g. restart -> respawn) |

The "graceful then hard" escalation in `start_component`/`restart_component`
becomes an ordered `remediations:` list in the policy: try the gentle one first,
escalate to the forceful one once attempts exceed its threshold.

---

## 2. Providers (WHERE)

| Legacy | Disposition | Target |
|--------|-------------|--------|
| `connexion.run_command` / `run_local_command` | DONE (Phase 0) | `providers/command.py::run_local` |
| `connexion.ssh_run_command` (string-built `ssh {SSH_OPTS} ...`) | DONE/REWRITE | `providers/host.py::SSHProvider` (already shells `ssh`; harden, add asyncssh later) |
| `connexion.timeout()` SIGALRM decorator | DROP | replaced by `subprocess.run(timeout=...)` already in command.py |
| `action_handler.Action` (local vs Worker-API vs ssh dispatch) | REWRITE | provider selection via `make_provider`; the master/worker-over-HTTP path is dropped (see §6) |
| `run_local_command` writing every command to a `Command` DB row | REWRITE (optional) | optional `Event(kind="command")` audit; off by default |
| `is_server_reachable` (ping), `is_ssh_connexion_ok`, `is_reachable_remotely` | PORT | `providers/host.py` reachability helper / a `PingProbe` |
| `is_port_used` / `is_bot_friendly` (curl to bot API) | PORT (port) / DROP (bot API) | `lsof`/socket check -> `PortProbe` (§3); curl-to-bot is dropped |

---

## 3. Probes (HOW) — implement first

All read-only; each returns `ProbeResult(healthy, detail)` and uses only
`provider.run(...)`. Priority order for Phase 1:

| Probe | Legacy source | Target | Notes |
|-------|---------------|--------|-------|
| **ProcessProbe** | `os_actions.get_process_pid` + `Handler.get_one_process_status` | `probes/host.py::ProcessProbe` | params: `name`, `user`, `filters`. Healthy iff >=1 matching pid. REWRITE the `ps … awk` pipeline into something `pgrep -f`-based; keep filter semantics. |
| **SystemdProbe** | `os_actions.is_service_running` / `is_service_exits` | `probes/host.py::SystemdProbe` | params: `unit`. Prefer `systemctl is-active`; legacy used `service … status` + grep `running\|demarre` — DROP the French-locale grep. |
| **PortProbe** | `connexion.is_port_used` (`lsof -i :PORT`) | `probes/host.py::PortProbe` | params: `port`, optional `host`. |
| **DiskProbe** (filesystem usage) | NEW (legacy only does RAID health, see below) | `probes/host.py::DiskProbe` | params: `path`, `threshold_pct`. `df`-based; this is the disk-fill probe the AI roadmap (Phase 3) predicts against. |
| **RaidDiskProbe** (hardware) | `node_handler.get_disk_infos` + `get_disk_data` (megacli) | PLUGIN `probes/hardware/` (optional) | megacli `PredictiveFailureCount>0`, `FirmwareState != Online`, media/other error counts. Hardware-specific; keep out of core Phase 1, ship as optional probe. |
| HttpProbe | implied by `is_bot_friendly` curl pattern | `probes/host.py::HttpProbe` (nice-to-have) | params: `url`, `expect_status`. |

The whole `hardware/` tree (`megacli`, `hpacucli`, `areca`, `ipmi`, `sensors`,
`smart_utils`, `bios_hp`, `infiniband`, `benchmark/*`) is **PLUGIN/DROP** for
Phase 1: not needed for process/service/port/disk-usage healing. Port only the
megacli RAID-health read if/when a hardware plugin is wanted.

---

## 4. Remediations (WHAT) — implement first

Each returns `RemediationResult(success, detail)`; carries an `autonomy` level.

| Remediation | Legacy source | Target | Autonomy default |
|-------------|---------------|--------|------------------|
| **RestartService** | `os_actions.action_over_service(host, svc, start/stop/restart)` + `Handler.start_stop_service` | `remediations/host.py::RestartService` | `gated` (low risk) |
| **RespawnProcess** | `Handler.start_stop_process` + `launch_tele_action` (`su - user -c "<cmd>"`) | `remediations/host.py::RespawnProcess` | `gated`; the "start command" comes from policy params (replaces `TeleAction.cmd`) |
| **KillProcess** | `os_actions.do_kill_processes` (`kill -9`) | `remediations/host.py::KillProcess` | `gated`; used as the forceful step of a stop/respawn |
| **RotateLogs / FreeDisk** | NEW (pairs with DiskProbe) | `remediations/host.py::RotateLogs` | `suggest` first (deleting data is high-risk) |
| RestartComponent (graceful->hard ladder) | `Handler.start_component` / `restart_component` | expressed as ordered remediation list, not a new type | — |
| Ambari start/stop/decommission | `ambari/*`, `change_handler.OpHandler` | PLUGIN (§6) | — |

**Tele-action model -> policy params.** Legacy stored a restart command per
component in the `TeleAction` table (`id_obj_alarm`, `user`, `cmd`). In Spero this
becomes `RemediationSpec.params` (e.g. `{user: hdfs, start: "...", stop: "..."}`)
in the YAML policy. The whole `save_tele_action` / `recover_one_tele_action` /
`register_tele_action` machinery is **DROP** (replaced by declarative policy).

---

## 5. Store / models

Spero already collapses the bot's `Node/Alert/Change/Operation/Command` into
`Node` + a single `Event` audit trail (`store/models.py`). Mapping:

| Legacy table (`db/model.py`) | Disposition | Target |
|------------------------------|-------------|--------|
| `Node` | PORT (slim) | `store/models.py::Node` (drop `node_type` master/worker, `install`, `current_version`) |
| `Component` + `NodeComponent` (the supervised surface, `auto_restart`, `nb_fails`, `category`) | REWRITE | the policy YAML *is* the supervised surface; `nb_fails` -> engine counter; `category` (worker/master/client) DROP (Hadoop role) |
| `Alert` (`state` NA/A, `count`) | REWRITE | `Event(kind="alert")` + an open/resolved alert concept in `alerting/` |
| `Operation` (start/stop audit) | REWRITE | `Event(kind="remediation")` |
| `Command` (every shell cmd logged) | REWRITE/optional | `Event(kind="command")`, opt-in |
| `Change` (node in/out of cluster) | DROP | Hadoop cluster lifecycle, not host healing |
| `TeleAction` | DROP | -> policy params (§4) |
| `SupFailureCounter` | REWRITE | engine failure counter / counters table |
| `MyDatabase` ctx mgr, raw `create_engine` sqlite | DROP | use existing `store/db.py` (SQLAlchemy 2.0) |

The `handle_alerts` / `handle_operation` decorators in `remote/utils.py`
(wrap an action, ack alerts on rc==0, save operation on failure) -> REWRITE as the
engine's post-remediation bookkeeping, not decorators.

---

## 6. Master/Worker, Ambari, Orange coupling — DROP or PLUGIN

**Master/Worker HTTP fabric — DROP for Phase 1.**
`remote/master.py`, `remote/worker.py`, `remote/communicate.py` (~1000 lines of
CRUD over a bespoke `/api/...` REST surface), `remote/Flask_auth.py`,
`remote/shutdown.py`, `remote/update_configs.py`, `commons/curl.py`,
`commons/crypto.py`, `commons/password.py`. This whole "replicate every DB row to
the active master over curl" model is replaced by a single control-plane DB +
FastAPI (`api/`). The `Communication.freeze/unfreeze` endpoints -> a `frozen`
toggle on the policy/API. SSH remains the only remote transport (SSHProvider);
agent-to-agent gossip is a post-Phase-1 concern.

**Ambari / Hadoop — PLUGIN (optional adapter).**
Entire `utilities/ambari/*` (`ambari.py`, `ambari_host.py`, `ambari_worker.py`,
`ambari_user.py`, `config.py`, `utils.py`), plus `wab.py` (Orange WAB/bastion),
`change_handler.py` (`node_in/out_cluster`, datanode decommission, disk
reconstruction via `DiskDiscovery`), and the `managed_by_ambari` branches inside
`node_handler.py`. None of this is core supervision. If wanted later, it becomes
an optional provider/remediation adapter (e.g. `spero.plugins.ambari`) behind the
same `Probe`/`Remediation` interfaces. The blackout/maintenance flag-file dance
(`put_blackout`/`remove_blackout`, `check_if_blackout_exists`) -> a generic
"maintenance" target state in core, dropping the Ambari/FlagBlackOut specifics.

**Orange-specific to strip everywhere:**
- `__copyright__ = "Orange France"` headers, `@orange.com` maintainer, `BASICAT`,
  `CLUSTER_ID`, `rouen.fr` hostnames, French log strings (`demarre`), GID/Patrol
  IDs.
- **Patrol/BMC integration** (`perform_patrol_supervision`,
  `perform_activate_patrol_config`, all `patrol_*.cfg` templating, `pconfig`,
  `OperatePatrolAll.sh`) — DROP entirely; this is the legacy enterprise monitoring
  bus, replaced by Spero's own alerting.
- `operate_node.py` CLI (`start_node/stop_node/status_node/start_component`) —
  REWRITE the *non-Ambari* parts as `spero heal <target>` CLI verbs over the
  engine; drop the node-in/out-of-cluster verbs.
- `mail.py`: SMTP send (`send_mail_from_server`) -> PORT into `alerting/` as an
  email channel (modern `email.message.EmailMessage`, the legacy `email.MIMEText`
  imports are Py2). `check_mail_has_been_sent` / maillog-scraping on a relay host
  -> DROP. `sending_mail_change/install` (cluster lifecycle) -> DROP;
  `sending_mail_alert/restart/incident` -> PORT as alert templates.
- `fstab.py` (Canonical GPL `Fstab`), `files.py` remote file ops, `ownership.py`,
  `install/*`, `parser/*` (argparse helpers), `hardware/*`, `checker.py`,
  `agent.py`, `bot.py`, `manage.py`, `human-dectect.py` — DROP for Phase 1 (CLI is
  Typer now; file ops only as needed by RotateLogs).

---

## 7. Alerting

| Legacy | Disposition | Target |
|--------|-------------|--------|
| `save_one_alert` / `acknowledge_one_alert` (create on first fail, increment count, resolve on recover, email on create) | REWRITE | `alerting/` open/resolve logic driven by the engine; this is the cleanest reusable idea in the bot |
| `sending_mail_alert` / `sending_mail_restart` / `sending_mail_incident` | PORT | `alerting/email.py` channel + templates |
| `JSON_CC_MAIL_ALERT` toggle, recipient lists | PORT | alerting config in `config.py` / policy |
| maillog verification, Patrol object alarms | DROP | — |

---

## 8. Concrete Phase-1 build order

1. `core/engine.py` — the probe->count->remediate->alert loop over a `Policy`
   (§1), honoring `frozen`, `max_attempts`, `autonomy`; persist `Event`s.
2. Probes: `ProcessProbe`, `SystemdProbe`, `PortProbe`, `DiskProbe`
   (`probes/host.py`).
3. Remediations: `RestartService`, `RespawnProcess`, `KillProcess`,
   `RotateLogs` (`remediations/host.py`).
4. A failure-counter + open-alert store (extend `store/`), and `alerting/email.py`.
5. CLI `spero heal`/`spero run` + API routers (`/targets` exists; add
   `/events`, `/alerts`, `/heal`).
6. Defer: RAID/hardware probes (plugin), Ambari adapter (plugin), agent
   master/worker fabric.

---

### Surprises / call-outs

- The bot already implements the exact "fail N times before auto-restart, with a
  global freeze and per-item opt-in" policy the spec describes — Spero's
  `Policy.frozen` + `RemediationSpec.max_attempts` + `Autonomy` is a faithful,
  cleaner re-encoding. The mapping is 1:1.
- Roughly half the legacy LOC (master/worker REST CRUD + Ambari + Patrol) is
  infrastructure plumbing that Spero's single-DB + FastAPI + SSH design deletes
  outright.
- The legacy "DiskProbe" is **RAID hardware health (megacli)**, not filesystem
  fill. Spero's intended DiskProbe (df/threshold) is effectively new code; the
  hardware check should be an optional plugin.
- The restart command lived in data (`TeleAction` rows) and was replicated across
  nodes; in Spero it lives in the declarative policy — a big simplification.
- Watch the shell-injection surface: legacy probes build `ps … awk` / `grep`
  pipelines with `shell=True`. Reimplement with `pgrep`/`systemctl is-active`/
  `lsof`/`df` argv-style through `run_local` (which already defaults to no-shell).
