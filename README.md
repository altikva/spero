# Spero

Self-healing supervision agent for Linux hosts and Kubernetes.

Spero watches the things you run — processes, services, disks, workloads — notices
when they break, and heals them under policy-governed autonomy. It sits between a
single-host tool like Monit and a full Prometheus + Alertmanager + Ansible stack:
lightweight, agent-based, cluster-aware, with an AI layer for prediction,
root-cause, and policy-gated remediation.

Shipped under [Altikva](https://altikva.com).

> Status: pre-alpha. Phase 1 (host self-healing) works end to end: an async
> provider layer (local + asyncssh), host probes (process, systemd, port, disk),
> remediations (restart, respawn, kill, rotate), and the supervision engine with
> failure counting, escalation, autonomy gating, and alerting -- all under test.

## Concepts

Spero is built on four seams so it spans hosts today and Kubernetes next without
re-architecting:

| Seam | Question | Examples |
|------|----------|----------|
| **Provider** | where things run | local, SSH host, Kubernetes |
| **Probe** | how you know it is healthy | process, systemd, port, disk, pod-ready |
| **Remediation** | what to do about it | restart, respawn, rotate, rollout, scale |
| **Policy** | the declared intent | YAML: target → probe → remediations + autonomy |

Remediations carry an **autonomy** level — `suggest`, `gated`, or `auto` — so
low-risk healing happens on its own while high-risk actions wait for a human.

## Quickstart

```bash
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"

spero status                       # show targets from policies/example.yaml
spero serve                        # run the control-plane API on :8800
pytest                             # run the suite
```

## Roadmap

- **Phase 0 — Foundations** *(done)*: Py3, FastAPI, policy model, host command layer, store, CI.
- **Phase 1 — Host self-healing** *(done)*: async providers, host probes + remediations, the supervision engine, alerting.
- **Phase 2 — Kubernetes**: a `k8s` provider with workload probes and remediations.
- **Phase 3 — AI**: predictive (disk-fill, flapping) → LLM root-cause → NL ops interface → agentic remediation.
- **Phase 4 — Data infra**: Kafka / Trino / ClickHouse / Postgres / Spark adapters.

## License

[Apache-2.0](./LICENSE).
