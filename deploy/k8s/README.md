# OpenMU on Kubernetes (one tenant)

Maps the supported **all-in-one** docker-compose stack (`deploy/all-in-one`) to
Kubernetes. ConnectServer, GameServer, ChatServer and the admin panel run in
**one** `munique/openmu` process (upstream distributed/Dapr compose is broken).
Dapr is not required and is **not** installed — this chart is namespace-scoped
only (safe on a shared kubeadm cluster).

Sized for a **2-CPU / 3.8Gi worker**: 1 replica each, total requests **75m CPU /
320Mi RAM** (Postgres 25m/64Mi + OpenMU 50m/256Mi). Limits 150m/256Mi +
400m/1024Mi so both pods can co-locate next to kube-system and Calico. No HPA.

Lab credentials (`postgres`/`admin`, admin panel `admin`/`openmu`) are for a
private lab only.

## Helm (preferred — one install = one isolated namespace)

```bash
# Local / generic cluster
helm install openmu deploy/helm/openmu -n openmu-lab --create-namespace

# Shared kubeadm lab (1 CP + 3 workers): keep pods off the control plane
helm install openmu deploy/helm/openmu -n openmu-lab --create-namespace \
  -f deploy/helm/openmu/values-lab.yaml
```

`--create-namespace` is the only cluster-scoped step; everything else lives in
`openmu-lab`. Useful `--set`: `serverName`, `resolveIP`, `postgres.auth.password`,
`admin.password`.

Uninstall:

```bash
helm uninstall openmu -n openmu-lab
kubectl delete ns openmu-lab
```

## kubectl / kustomize

```bash
kubectl apply -k deploy/k8s
```

If PVCs stay Pending (no default StorageClass), Helm with
`--set postgres.persistence.enabled=false --set openmu.persistence.adminKeys.enabled=false`
(emptyDir; data is lost on restart). Do not install a cluster-wide provisioner
from this chart.

## kind (local)

```bash
kind create cluster --config deploy/k8s/kind-config.yaml
kubectl apply -k deploy/k8s
```

Single-node kind **is** the control plane: do not use `values-lab.yaml`. For a
same-machine client: `--set resolveIP=loopback` and connect to `127.127.127.127`
(not `127.0.0.1`).

## k3s / minikube

```bash
kubectl apply -k deploy/k8s
# minikube: hostPort is on the VM — minikube ip
```

## Port exposure

| Port | Process | Lab default |
|---|---|---|
| 44405 TCP | ConnectServer (original client) | `hostPort` on the worker running the OpenMU pod |
| 44406 TCP | ConnectServer (open-source client) | `hostPort` |
| 55901–55906 TCP | GameServer | `hostPort` |
| 55980 TCP | ChatServer | `hostPort` |
| 8080 HTTP | Admin panel | Service NodePort **30080** (default 30000–32767 range) |

OpenMU is TCP-only; UDP is not mapped.

`hostPort` keeps player ports matching the OpenMU database (stock NodePort cannot
bind 44405). On a 3-worker lab the client must use **that worker’s public IP**
(`status.hostIP` / log line `RESOLVE_IP`), not a random worker and not the CP.
Empty `resolveIP` advertises `status.hostIP`. Do not set `resolveIP=local` in
Kubernetes (Pod IP).

Alternative: `--set service.hostPort=false --set service.type=NodePort` and then
change advertised ports in the admin panel to the 30xxx nodePorts.

## After apply

First Season 6 seed can take several minutes on a 2-CPU worker:

```bash
kubectl -n openmu-lab get pods -w
kubectl -n openmu-lab logs -l app.kubernetes.io/component=openmu -f
```

Admin panel: `http://<any-node-ip>:30080` (user `admin` / password `openmu`).
