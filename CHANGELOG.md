# Changelog

All notable changes to Spero are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project aims to
follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

[0.1.0]: https://github.com/altikva/spero/releases/tag/v0.1.0
