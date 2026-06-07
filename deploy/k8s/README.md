# Spero in-cluster deployment

Run spero as an always-on supervisor inside a Kubernetes cluster. The manifests
here are Kustomize: a read-only base, and an `acting` overlay that opts into
remediation.

## Layout

```
deploy/k8s/
  base/                supervise-only: read RBAC + always-on Deployment
  overlays/acting/     base + mutating RBAC (lets spero remediate)
```

## Supervise-only base vs acting overlay

The base grants read access only (get, list, watch) to the resources the probes
read: pods, pod metrics (metrics.k8s.io), deployments (apps), KEDA
ScaledObjects (keda.sh), elpio resources (elpio.io), and Knative
Serving services and revisions (serving.knative.dev). With the base alone, spero
observes and reports but cannot change anything in the cluster, even if a policy
declares remediations.

The `acting` overlay adds a second ClusterRole (`spero-remediator`) and binding
on top of the base. It grants exactly the mutating verbs spero needs: patch
deployments, get/patch/update deployments/scale, delete pods, patch
ScaledObjects. It also grants coordination.k8s.io leases (get, create, update)
for leader election, so only one replica acts at a time. The base never carries
mutating verbs: acting is always an explicit opt-in.

## Apply

Supervise only:

```
kubectl apply -k deploy/k8s/base
```

Let spero act:

```
kubectl apply -k deploy/k8s/overlays/acting
```

Render without applying (review the YAML first):

```
kubectl kustomize deploy/k8s/base
kubectl kustomize deploy/k8s/overlays/acting
```

## Image

No image is published yet. Build and push it before applying, then point the
Deployment at your registry (the manifests reference `ghcr.io/altikva/spero:0.2.0`):

```
docker build -t ghcr.io/altikva/spero:0.2.0 .
docker push ghcr.io/altikva/spero:0.2.0
```

The image carries the spero package plus a pinned `kubectl` binary, because the
Kubernetes provider shells out to `kubectl` at runtime (it does not use a python
client). It runs as a non-root user (uid 65532) with a read-only root
filesystem.

## Observe a running worker

The Deployment runs `spero serve`, which supervises the cluster AND exposes its
live state over HTTP on port 8800: `/status` (per-target health and the last
action), `/events` (recent probe and remediation events), `/objects/{target}`
(the target's object as YAML), and `/logs/{target}?tail=N` (the last N log lines
of the target's pods). It serves store-less, so nothing is written under the
read-only root filesystem.

Watch it from your laptop by port-forwarding to the pod, then pointing a local
spero at it:

```
kubectl -n spero-system port-forward deploy/spero 8800:8800
spero top --remote http://localhost:8800
```

`spero top --remote` polls those endpoints and renders the same dashboard, so you
see what the in-cluster worker is supervising without running any probes yourself.
With the `tui` extra, `i` inspects a target's YAML and `l` tails its pod logs over
those same endpoints (the `s` shell convenience is local-only: it would need a TTY
tunnel through the agent, which dial-home deliberately does not open). This is the
pull-based read model; the dial-home design below is the push-based version where
the worker reaches out to a remote owner.

## Dial-home (implemented)

The dial-home path is real: run the fleet owner with `spero owner` (a service the
agents reach), and run the in-cluster worker as `spero agent --owner <url>` instead
of `spero serve`. The agent supervises locally and POSTs its status + events to the
owner on a timer; the response carries orders. A gated remediation waits for the
owner via a RemoteApprover (the engine's existing approver slot), so a human approves
a target's action with `POST /agents/<id>/approve {"target": "<name>"}` and the next
agent report applies it. `auto` actions still run unattended even if the owner is
offline. To use it in-cluster, set the Deployment args to
`["agent", "--owner", "$(SPERO_OWNER_URL)", "--policy", "/etc/spero/policy.yaml"]`.

## Dial-home design

Spero runs as a plain always-on Deployment, not a Knative scale-to-zero service.
A supervisor has to stay up: if it scaled to zero, nothing would be watching when
a workload degrades. So `replicas: 1`, leader election guards against an
accidental scaleup, and the pod is hardened (non-root, read-only root fs, all
capabilities dropped, RuntimeDefault seccomp).

Spero works standalone. With the `acting` overlay it can auto-remediate the
failures its policy marks as automatic, and gate the riskier ones, with no
outside dependency. That is the floor, not the ceiling.

On top of standalone operation, spero dials OUT to a remote owner over a
persistent connection. The direction matters: the owner can never reach inbound
into the cluster (no ingress, no NodePort, no firewall holes). The agent opens
the connection from inside and keeps it open. Set the target with the
`SPERO_OWNER_URL` env var; each agent identifies itself with `SPERO_AGENT_ID`
(wired here to the pod name via the downward API).

Over that connection the owner does two things:

- Answers gated remediations as a REMOTE approver. It drops straight into the
  engine's existing `approver` slot, the same slot a human or the AI approver
  fills. So a gated action can wait for a yes/no from the owner before it runs.
- Pushes policy updates. The owner can ship a new policy to a running agent
  without a redeploy.

The worker streams events back to the owner as feedback (probe results,
remediation outcomes, approvals), so the owner has a live view of every cluster
it supervises. Knative Eventing / CloudEvents is an optional transport for that
feedback bus: useful if you already run Knative Eventing, not required for the
core dial-home path.
