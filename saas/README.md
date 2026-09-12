# OpenMU SaaS control plane

Lightweight FastAPI + React admin for a **one-tenant Kubernetes lab**. Code lives only under `saas/`. It does not change OpenMU `src/`, `tests/`, `deploy/k8s/`, or `deploy/helm/`.

The intended cluster API (not a secret) is:

`https://api.test-01.k8s.t-h.cloud:6443`

(same endpoint on the control-plane public IP: `https://62.216.75.149:6443`). Auth is **not** in this repo. Point the Python client at a **local kubeconfig path** when credentials exist.

## How to run locally

### Backend

Python 3.11+. From `saas/backend`:

```bash
python3 -m venv .venv && source .venv/bin/activate   # or: pip install --user -e ".[dev]"
pip install -e ".[dev]"
cp .env.example .env   # optional; do not put tokens or passwords in git
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

- API docs: http://127.0.0.1:8000/docs
- Health: http://127.0.0.1:8000/api/health

Without a kubeconfig the API stays up and returns structured errors (`cluster_unavailable`) instead of crashing.

### Frontend

From `saas/frontend` (Node 20+):

```bash
npm install
npm run dev
```

Panel: http://127.0.0.1:5173 — Vite proxies `/api` to the FastAPI process.

### Kubernetes credentials (when available)

Do **not** commit kubeconfig, client certs, tokens, or SSH keys.

```bash
export SAAS_KUBECONFIG=/path/to/lab.kubeconfig   # or KUBECONFIG
export SAAS_KUBE_CONTEXT=test-01                 # optional
export SAAS_K8S_API_SERVER=https://api.test-01.k8s.t-h.cloud:6443
```

The kubeconfig `clusters[].cluster.server` should be that `:6443` URL. FastAPI loads **only** from `SAAS_KUBECONFIG` / `KUBECONFIG` (then in-cluster if the panel itself is a pod). It does **not** read `~/.kube/config`, `admin.conf`, or SSH keys.

This is a **shared kubeadm** lab: every Kubernetes call is namespaced to `SAAS_LAB_NAMESPACE` (`openmu-lab`). The client never lists namespaces or nodes, never touches `kube-system`, and provision/restart refuse any other namespace. `replicas` is fixed at `1`.

```bash
export SAAS_LAB_NAMESPACE=openmu-lab
export SAAS_K8S_NODE_IP=185.126.137.16   # optional NodePort display; workers are not listed
```

### Tenant PostgreSQL

Game-parameter routes talk to OpenMU’s `config` schema when a DSN is available:

| Variable | Default | Purpose |
|---|---|---|
| `SAAS_PG_HOST` | unset | Tenant Postgres host |
| `SAAS_PG_PORT` | `5432` | Port |
| `SAAS_PG_DATABASE` | `openmu` | Database name |
| `SAAS_PG_USER` | `postgres` | User |
| `SAAS_PG_PASSWORD` | unset | Password (local `.env` only) |
| `SAAS_PG_DSN` | unset | Full URI override |
| `SAAS_PG_DSN_<NAMESPACE>` | unset | Per-tenant URI (`openmu-lab` → `SAAS_PG_DSN_OPENMU_LAB`) |

If the cluster is connected, the API also looks for a `postgres` / `postgresql` / `database` / `openmu-db` Service or Secret **in that tenant namespace only**. GET endpoints still return the JSON shape with `source=defaults` when the database is missing.

## API

| Method | Path | Notes |
|---|---|---|
| GET | `/api/health` | Cluster + DB; includes intended `api_server` and kubeconfig **path** only |
| GET | `/api/tenants`, `/api/servers` | Lab tenant list (empty + error if no credentials) |
| GET | `/api/tenants/{ns}` | Pods, deployments, Service IP/port |
| GET | `/api/tenants/{ns}/pods` | OpenMU-related pods (`Running` / `Stopped` / `Crash` / …) |
| GET | `/api/tenants/{ns}/pods/{name}` | Single pod |
| POST | `/api/tenants/{ns}/pods/{name}/restart` | Delete pod in the lab namespace only |
| GET | `/api/tenants/{ns}/deployments` | Deployments |
| POST | `/api/tenants/{ns}/deployments/{name}/restart` | Rollout restart (1 replica) |
| GET | `/api/tenants/{ns}/endpoints` | Assigned IP / NodePort / LoadBalancer |
| GET/PUT | `/api/tenants/{ns}/game/rates` | `GameConfiguration` rates/drops flags |
| GET | `/api/tenants/{ns}/game/drops` | `DropItemGroup` |
| PUT | `/api/tenants/{ns}/game/drops/{id}` | Update chance |
| GET | `/api/tenants/{ns}/game/spawns` | `MonsterSpawnArea` |
| PUT | `/api/tenants/{ns}/game/spawns/{id}` | Update quantity |
| GET | `/api/tenants/{ns}/game/events` | `MiniGameDefinition` |
| PUT | `/api/tenants/{ns}/game/events/{id}` | Update fee / player cap |
| POST | `/api/servers` | **Stub** — validates provision body, returns **501** (no Helm install) |

Provision request model: `server_name`, `ports` (`connect`/`game`/`chat`/`admin`), `database` (`host` optional, `name`, `user`, `password`), `replicas` (lab: `1`).

## Still stubbed

- **Helm install** (`POST /api/servers`) — charts belong to `deploy/helm/`; this API only validates and refuses extra tenants.
- **Live cluster calls** until a kubeconfig path is provided.
- **PostgreSQL writes** until `SAAS_PG_*` (or an in-namespace postgres Service) is configured.

## Tests

```bash
cd saas/backend
pytest
```
