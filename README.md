# Spero

Self-healing supervision agent for Linux hosts and Kubernetes.

Spero watches the things you run — processes, services, disks, workloads — notices
when they break, and heals them under policy-governed autonomy. It sits between a
single-host tool like Monit and a full Prometheus + Alertmanager + Ansible stack:
lightweight, agent-based, cluster-aware, with an AI layer for prediction,
root-cause, and policy-gated remediation.

Shipped under [Altikva](https://altikva.com).

> Status: pre-alpha, but the spine is complete. Spero supervises and heals Linux
> hosts (local + asyncssh) and Kubernetes (kubectl) through one engine, with an AI
> layer for prediction, root-cause, natural-language queries, and agentic
> (policy-gated) remediation. 91 tests, ruff + mypy clean.

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
spero run                          # run one supervision cycle
spero watch                        # supervise continuously (each target on its interval)
spero watch --ai-approve           # agentic: the model decides gated remediations
spero heal nginx                   # probe one target, walk its remediations interactively
spero ask "what flapped today?"    # natural-language query over the event history
spero serve                        # run the control-plane API on :8800
pytest                             # run the suite
```

## Roadmap

- **Phase 0 — Foundations** *(done)*: Py3, FastAPI, policy model, host command layer, store, CI.
- **Phase 1 — Host self-healing** *(done)*: async providers, host probes + remediations, the supervision engine, alerting.
- **Phase 2 — Kubernetes** *(done)*: a `k8s` provider (kubectl) with pod/deployment probes and rollout-restart / scale / delete-pod remediations.
- **Phase 3 — AI** *(done)*: predictive (disk-fill forecast, flapping), LLM root-cause + incident summaries, NL ops queries (`spero ask`), and agentic remediation (`spero run --ai-approve`). Claude-backed, works without a key via a fallback.
- **Phase 4 — Data infra** *(done)*: composable `http` + `command` probes and named adapters (`postgres`, `kafka`, `trino`, `clickhouse`), healed by the existing restart / rollout-restart remediations.

## License

[Apache-2.0](./LICENSE).
