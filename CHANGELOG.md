<!--
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# __creation__ = 2026-06-03
# __author__ = "jndjama (Joy Ndjama)"
# __copyright__ = "Copyright 2026 ALTIKVA."
# __licence__ = "MIT & CC BY-NC-SA (https://www.altikva.com/licenses/LICENSE-1.0)"
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# Description: Changelog: notable changes to Spero per release (Keep a Changelog format).
-->

# Changelog

All notable changes to Spero are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project aims to
follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] - 2026-06-07

### Added

- **In-cluster deployment**: a multi-stage `Dockerfile` (the spero package plus a
  pinned kubectl, non-root uid 65532, read-only root filesystem) and Kustomize
  manifests under `deploy/k8s/` — a supervise-only `base` (read RBAC) and an `acting`
  overlay that adds exactly the mutating verbs spero needs plus leader-election leases.
  RBAC is scoped to the resources the probes read.
- **Remote observe**: `spero serve` now exposes its live state over HTTP
  (`/status`, `/events`), and `spero top --remote <url>` renders that same dashboard
  from your laptop without running any probes locally.
- **Inspect and logs in `spero top`** (with the `tui` extra): `i` shows a target's
  object as YAML and `l` tails its pod logs, both served over `/objects/{target}` and
  `/logs/{target}` so they work locally and over `--remote`.
- **Local shell convenience**: `s` in `spero top` shells into a target's pod with
  your own kubectl (`kubectl exec -it`). Local only by design — it uses your
  kubeconfig, not the agent's RBAC, and is never offered over `--remote` or dial-home.
- **Dial-home**: `spero owner` runs a fleet service that in-cluster `spero agent`
  workers dial out to; the agent supervises locally, reports status + events on a
  timer, and a `RemoteApprover` lets the owner answer gated remediations. `auto`
  actions still run unattended if the owner is unreachable.
- **`knative-service` probe** (experimental): supervises a `serving.knative.dev`
  Service by its rolled-up `Ready` condition.
- **`--version` flag** on the root command (alongside the existing `spero version`).

### Changed

- The Textual `spero top` footer shows `ctrl+p` for the command palette instead of
  the cryptic `^p`, and table cells render as literal text so paths/URLs are no longer
  mis-underlined as links.

### Fixed

- Aligned the elpio probes and the in-cluster RBAC to elpio v0.1.0's real CRD group
  (`elpio.io`), verified against the live operator.

## [0.2.0] - 2026-06-05

### Added

- **`spero top`**: a live supervision dashboard. A target grid (health, failure
  count, last action and status) plus a rolling event feed, refreshed on a timer.
  Interactive: approve a gated remediation inline, pause, refresh, toggle the action
  freeze, quit. With the optional `tui` extra it runs a Textual UI (mouse, row
  selection, scrollback); without it, a rich.Live dashboard, so the command always works.
- **Elpio supervision probes** (experimental): `elpio-service`, `elpio-function`,
  and `elpio-task` supervise elpio's serverless custom resources by their
  Knative/KEDA-style Ready condition. Healing stays elpio's operator's job.
- **KEDA probe and remediation** (experimental): `keda-scaledobject` (unhealthy when
  a ScaledObject is paused or not Ready) and `keda-unpause` (clears KEDA's pause
  annotations). Validated against live KEDA on minikube.
- **`resource-usage` probe**: flags pods whose live CPU or memory usage exceeds a
  configurable percent of their declared requests. A metrics-server-backed
  rightsizing signal; read-only, acting on it stays a future gated remediation.
- **Branded CLI**: a figlet banner and a landing screen on bare `spero` (commands and
  examples), plus the banner as a header before every command.

### Changed

- Bare `spero` prints help and exits 0 instead of raising a "Missing command" error.
  The per-command banner goes to stderr, so stdout stays clean for piping.
- CI runs the full Python 3.11 to 3.14 matrix from a committed `uv.lock` for
  reproducible installs, alongside a non-gating job against the newest dependencies.
  Added gitleaks and ruff to a pre-commit config.
- Renamed the internal `a4c` references to `elpio` (the product's new name).

### Fixed

- The KEDA probe now treats a paused ScaledObject as unhealthy. Pausing leaves
  `Ready=True`, so a Ready-only check missed it and the heal never fired. Caught
  during live validation.
- The release workflow passes `--repo` to `gh release create` (the publish job has no
  checkout), so the GitHub Release step no longer fails after a successful PyPI upload.

## [0.1.0] - 2026-06-03

### Added

- **Supervision engine** — declarative YAML policy (target → probe → remediations)
  with per-remediation autonomy (`suggest` / `gated` / `auto`), failure counting,
  an escalation ladder, a global action freeze, and an event/audit store.
- **Providers** — `local` and `ssh:[user@]host[:port]` (asyncssh), and
  `k8s:[context][/namespace]` (kubectl). All async, behind one interface.
- **Probes** — host: `process`, `systemd`, `port`, `disk`; kubernetes: `pod`,
  `deployment`; data-infra: `http`, `command`, `postgres`, `kafka`, `trino`,
  `clickhouse`.
- **Remediations** — `restart`, `respawn`, `kill`, `rotate` (host); `rollout-restart`,
  `scale`, `delete-pod` (kubernetes). Destructive actions cannot run unattended.
- **Continuous watch daemon** — `spero watch`, one scheduled job per target at its
  own interval, graceful shutdown, event persistence.
- **AI layer** — predictive disk-fill forecast and flapping detection; LLM
  root-cause and incident summaries; natural-language queries over the event
  history (`spero ask`); agentic remediation (`spero run/watch --ai-approve`).
  Claude-backed, fully functional offline via a no-model fallback.
- **CLI** — `status`, `run`, `watch`, `heal`, `ask`, `diagnose`, `forecast`, `serve`.
- **Control plane** — FastAPI app with `/health` and `/targets`.

[0.3.0]: https://github.com/altikva/spero/releases/tag/v0.3.0
[0.2.0]: https://github.com/altikva/spero/releases/tag/v0.2.0
[0.1.0]: https://github.com/altikva/spero/releases/tag/v0.1.0
