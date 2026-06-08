<!--
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# __creation__ = 2026-06-09
# __author__ = "jndjama (Joy Ndjama)"
# __copyright__ = "Copyright 2026 ALTIKVA."
# __licence__ = "MIT & CC BY-NC-SA (https://www.altikva.com/licenses/LICENSE-1.0)"
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# Description: ADR-0001 -- whether spero should broker authenticated, audited
#              sessions into pods/VMs over the dial-home tunnel (a Tier B bastion).
-->

# ADR-0001: Brokered access (Tier B bastion) over the dial-home tunnel

- **Status:** Proposed (not decided). Tier A shipped; Tier B is deferred pending this decision.
- **Date:** 2026-06-09
- **Deciders:** maintainer (jndjama)
- **Supersedes / superseded by:** none

## Context

Spero already carries most of what an access broker needs as a side effect of
supervision:

- **A reachability inventory.** Every policy target declares both what it is and how
  to reach it: `parse_provider_spec` resolves `local`, `ssh:[user@]host[:port]`, and
  `k8s:[context]/[namespace]`. The hardest cold-start problem for a bastion (what
  exists, where, how to connect) is solved already.
- **Connection primitives.** `providers/host.py` opens asyncssh sessions;
  `core/shell.py` builds `kubectl exec` / `ssh` argv.
- **A reverse path.** `spero agent` runs inside clusters/networks that accept no
  inbound and dials OUT to a `spero owner` on a timer, pulling orders. Reaching
  workloads you cannot route to is the same trick modern bastions use (Teleport,
  Boundary, Tailscale SSH) with reverse tunnels.

Against that, the v0.4.0 security audit set a deliberate posture: the in-cluster
agent is least-privilege and read-mostly, `pods/exec` was kept OUT of its RBAC, and
interactive exec was made a LOCAL convenience that uses the operator's own kubeconfig
(see Tier A). A broker inverts that posture by design.

The request that prompted this ADR: "what if spero is also a sort of bastion to
connect to VMs or pods?" That splits cleanly into two tiers.

### Tier A -- a unified operator console (SHIPPED)

In `spero top`, the `s` key opens a session into the selected target with the
operator's OWN tools: `kubectl exec -it` for a pod, `ssh -t` for a host, a local
shell for a local target (`core/shell.py:connect_argv`). It brokers nothing, grants
no new privilege, and uses no spero-held credentials; access stays bounded by the
operator's kubeconfig / ssh config. It is local-only (never over `--remote` or
dial-home). This ADR does not relitigate Tier A; it is the baseline.

### Tier B -- a brokered bastion (THIS ADR)

spero authenticates *users*, authorizes who may reach which target, brokers an
interactive session (including into clusters the user cannot route to, via the
dial-home tunnel), records it, and issues short-lived credentials. This is a
different product category with mature incumbents.

## Decision

**Proposed: do NOT build Tier B as part of the supervision product by default.**
Ship Tier A (done) and, for true brokered access, integrate with / point users at an
existing access plane (Teleport, Boundary, AWS SSM, Tailscale SSH).

Build Tier B only as an explicit, separately-opted-in module IF the "bastion into
unreachable clusters via the agent's reverse tunnel" wedge is a deliberate strategic
bet -- and only with the security gates below treated as blocking requirements, not
follow-ups.

## Proposed design (if Tier B is pursued)

```
operator ──auth──▶  spero owner (access plane)  ◀──reverse tunnel──  spero agent ──exec──▶ pod / VM
            (OIDC)        authz + audit                (dials OUT)         (in-cluster)
```

1. **Transport.** Today's dial-home is HTTP request/response (report + orders) -- not
   a session transport. Tier B needs a persistent, bidirectional, low-latency stream
   so a PTY can flow operator ↔ owner ↔ agent ↔ target. Options:
   - a websocket upgrade on the agent's outbound connection (no new inbound, reuses
     the dial-home direction), or
   - a dedicated SSH reverse tunnel the agent opens to the owner.
   The agent runs the actual `kubectl exec -it` / local exec and pipes stdio over the
   tunnel; the owner relays it to the authenticated operator.
2. **Identity (authn).** Replace/augment the shared bearer token with per-user OIDC
   (SSO), and give agents verifiable identity rather than a self-asserted `--id`.
3. **Authorization (authz).** Per-user → per-target policy (who may reach what, with
   which shell/verbs), just-in-time and time-boxed grants, and an approval workflow
   for sensitive targets -- the existing gated-remediation approval machinery
   (Approver seam, owner approve orders) is a natural fit to reuse.
4. **Audit + recording.** Full session recording (asciinema-style cast), plus
   who/what/when in the event store. This is the entire compliance reason bastions
   exist (PCI-DSS, SOC 2, ISO 27001).
5. **Credentials.** Short-lived only (SSH certs, exec tokens); no standing secrets.
   The agent would need `pods/exec` RBAC -- the exact privilege the audit withheld.

## Security requirements (blocking, not optional)

Tier B makes spero the highest-value target in the environment: a compromised broker
is lateral access to everything it fronts. Non-negotiable before any rollout:

- Per-user identity + MFA; no shared secrets for human access.
- Per-user, per-target authorization; deny by default; JIT/time-boxed grants.
- No standing credentials; everything short-lived and revocable.
- Tamper-evident session recording and an immutable audit trail.
- Bounded agent blast radius (one cluster per agent, scoped exec, kill-switch).
- A break-glass path that is itself audited.
- Threat-modeled and pen-tested before it fronts anything real.

This is a much higher bar than SEC-1..7 cleared, and it re-opens all of them.

## Alternatives considered

1. **Tier A only (status quo after this work).** Operators reach targets with their
   own VPN/kubeconfig/ssh; spero is the console, not the access path. Lowest risk,
   keeps the product identity. The recommended default.
2. **Integrate, don't build.** Treat Teleport / Boundary / AWS SSM / Tailscale as the
   access plane and have spero deep-link into them (open a recorded session in the
   incumbent from `spero top`). Gets the value without owning the security surface.
3. **Mesh networking (Tailscale / WireGuard) + their SSH.** Solves reachability and
   identity with a proven stack; spero stays supervision-only.
4. **Build Tier B (this proposal's conditional path).** Differentiated only by the
   reverse-tunnel-into-unreachable-clusters wedge; otherwise a less mature Teleport.

## Consequences

- **Product identity shift.** "Self-healing supervision agent" becomes "supervision +
  access plane." That is a strategic repositioning, not a feature.
- **Security surface.** A standing, privileged, internet-adjacent session broker --
  the opposite of the hardened, read-mostly posture just established.
- **Maintenance + competition.** Months of work and ongoing security ownership,
  against well-funded incumbents whose whole job this is.
- **The one real upside.** The dial-home reverse tunnel makes "bastion into clusters
  you cannot ingress into" genuinely differentiated. If that specific pain is the
  bet, it is worth a real design; if not, Tier A + integration wins.

## Open questions

- Is "access into unreachable clusters" a pain the target users will pay for, or do
  they already run Teleport/SSM?
- Could Tier B ship as a thin relay in front of an incumbent (spero owns inventory +
  reverse tunnel; the incumbent owns identity, recording, compliance)?
- Does adding a privileged session path violate constraints in regulated environments
  (e.g. an Orange-style enterprise) that spero is otherwise designed to fit?
