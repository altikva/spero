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

## Install

```bash
pip install spero            # or: uv pip install spero
pip install "spero[ai]"      # add the Claude-backed AI layer
pip install "spero[k8s]"     # add the Kubernetes provider deps
```

## Quickstart

```bash
spero status                       # show targets from policies/example.yaml
spero run                          # run one supervision cycle
spero watch                        # supervise continuously (each target on its interval)
spero watch --ai-approve           # agentic: the model decides gated remediations
spero heal nginx                   # probe one target, walk its remediations interactively
spero ask "what flapped today?"    # natural-language query over the event history
spero serve                        # run the control-plane API on :8800
```

## From source

```bash
git clone https://github.com/altikva/spero && cd spero
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
pytest                             # run the suite
```

## License

Spero is released under the **ALTIKVA Dual License v1.0**
([MIT](./LICENSE) and [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/)),
SPDX `MIT AND CC-BY-NC-SA-4.0`. See [LICENSE](./LICENSE).
