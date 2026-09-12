"""Single-process FastAPI app for the OpenMU lab control plane."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.cluster import Cluster
from app.errors import LabGuard
from app.models import (
    ClusterHealth,
    DatabaseHealth,
    DropGroup,
    DropGroupUpdate,
    DropListResponse,
    EventListResponse,
    EventUpdate,
    GameEvent,
    GameRates,
    HealthResponse,
    ProvisionServerRequest,
    ProvisionServerResponse,
    RestartRequest,
    RestartResponse,
    SpawnArea,
    SpawnListResponse,
    SpawnUpdate,
    TenantDetail,
    TenantListResponse,
)
from app.postgres import GameStore, required_env_message
from app.settings import get_settings

settings = get_settings()
cluster = Cluster(settings)
store = GameStore(cluster, settings)

app = FastAPI(
    title=settings.api_title,
    version=__version__,
    description=(
        "Lightweight admin API for a one-tenant OpenMU Kubernetes lab. "
        "Talks to the cluster when credentials exist; otherwise returns "
        "clear 503 payloads. Helm install is not implemented here."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    db_error = None if settings.pg_configured() else required_env_message()
    kube_ok = cluster.connected
    return HealthResponse(
        status="ok" if kube_ok else "degraded",
        kubernetes=ClusterHealth(
            connected=kube_ok,
            mode=cluster.mode,
            error=None if kube_ok else cluster.error,
            lab_mode=settings.lab_mode,
            lab_namespace=settings.lab_namespace,
            api_server=cluster.active_api_server or settings.k8s_api_server,
            kubeconfig_path=cluster.kubeconfig_path,
        ),
        database=DatabaseHealth(
            configured=settings.pg_configured(),
            host=settings.pg_host,
            port=settings.pg_port,
            database=settings.pg_database,
            user=settings.pg_user,
            error=db_error,
        ),
    )


@app.get("/api/tenants", response_model=TenantListResponse)
@app.get("/api/servers", response_model=TenantListResponse)
def list_tenants() -> TenantListResponse:
    if not cluster.connected:
        return TenantListResponse(
            cluster_connected=False,
            cluster_error=cluster.error,
            lab_mode=settings.lab_mode,
            lab_namespace=settings.lab_namespace,
            tenants=[],
        )
    tenants = cluster.list_tenants()
    return TenantListResponse(
        cluster_connected=True,
        lab_mode=settings.lab_mode,
        lab_namespace=settings.lab_namespace,
        tenants=tenants,
    )


@app.get("/api/tenants/{namespace}", response_model=TenantDetail)
def get_tenant(namespace: str) -> TenantDetail:
    return cluster.get_tenant(namespace)


@app.get("/api/tenants/{namespace}/pods")
def list_pods(namespace: str) -> dict:
    return {"items": cluster.list_pods(namespace)}


@app.get("/api/tenants/{namespace}/pods/{name}")
def get_pod(namespace: str, name: str) -> dict:
    return cluster.get_pod(namespace, name).model_dump()


@app.post("/api/tenants/{namespace}/pods/{name}/restart", response_model=RestartResponse)
def restart_pod(namespace: str, name: str, body: RestartRequest | None = None) -> RestartResponse:
    cluster.restart_pod(namespace, name)
    note = body.reason if body else None
    return RestartResponse(
        namespace=namespace,
        kind="Pod",
        name=name,
        action="deleted",
        message=f"Pod {name} deleted so its controller can recreate it."
        + (f" Reason: {note}" if note else ""),
    )


@app.get("/api/tenants/{namespace}/deployments")
def list_deployments(namespace: str) -> dict:
    return {"items": cluster.list_deployments(namespace)}


@app.post("/api/tenants/{namespace}/deployments/{name}/restart", response_model=RestartResponse)
def restart_deployment(namespace: str, name: str, body: RestartRequest | None = None) -> RestartResponse:
    cluster.restart_deployment(namespace, name)
    note = body.reason if body else None
    return RestartResponse(
        namespace=namespace,
        kind="Deployment",
        name=name,
        action="rolled",
        message=f"Deployment {name} patched with restartedAt (1 replica lab rollout)."
        + (f" Reason: {note}" if note else ""),
    )


@app.get("/api/tenants/{namespace}/endpoints")
def list_endpoints(namespace: str) -> dict:
    return {"items": cluster.list_endpoints(namespace)}


@app.get("/api/tenants/{namespace}/game/rates", response_model=GameRates)
def get_rates(namespace: str) -> GameRates:
    _guard_ns(namespace)
    return store.get_rates(namespace)


@app.put("/api/tenants/{namespace}/game/rates", response_model=GameRates)
def put_rates(namespace: str, rates: GameRates) -> GameRates:
    _guard_ns(namespace)
    payload = rates.model_copy(update={"source": "postgresql", "persisted": False, "database_error": None})
    return store.put_rates(namespace, payload)


@app.get("/api/tenants/{namespace}/game/drops", response_model=DropListResponse)
def get_drops(namespace: str) -> DropListResponse:
    _guard_ns(namespace)
    return store.list_drops(namespace)


@app.put("/api/tenants/{namespace}/game/drops/{drop_id}", response_model=DropGroup)
def put_drop(namespace: str, drop_id: str, update: DropGroupUpdate) -> DropGroup:
    _guard_ns(namespace)
    return store.update_drop(namespace, drop_id, update)


@app.get("/api/tenants/{namespace}/game/spawns", response_model=SpawnListResponse)
def get_spawns(namespace: str) -> SpawnListResponse:
    _guard_ns(namespace)
    return store.list_spawns(namespace)


@app.put("/api/tenants/{namespace}/game/spawns/{spawn_id}", response_model=SpawnArea)
def put_spawn(namespace: str, spawn_id: str, update: SpawnUpdate) -> SpawnArea:
    _guard_ns(namespace)
    return store.update_spawn(namespace, spawn_id, update)


@app.get("/api/tenants/{namespace}/game/events", response_model=EventListResponse)
def get_events(namespace: str) -> EventListResponse:
    _guard_ns(namespace)
    return store.list_events(namespace)


@app.put("/api/tenants/{namespace}/game/events/{event_id}", response_model=GameEvent)
def put_event(namespace: str, event_id: str, update: EventUpdate) -> GameEvent:
    _guard_ns(namespace)
    return store.update_event(namespace, event_id, update)


@app.post("/api/servers", response_model=ProvisionServerResponse)
def provision_server(request: ProvisionServerRequest) -> JSONResponse:
    namespace = cluster.namespace_for_server_name(request.server_name)
    if request.replicas != 1:
        raise LabGuard("Lab provision only allows replicas=1.")
    if settings.lab_mode and request.server_name not in {settings.lab_namespace, settings.lab_namespace.removeprefix("openmu-")}:
        # Keep the request model intact but pin the namespace to the lab tenant.
        namespace = settings.lab_namespace

    if cluster.connected:
        existing = cluster.existing_tenant_count()
        if existing >= settings.max_tenants:
            raise LabGuard(
                f"Lab already has {existing} tenant(s). Provisioning a second "
                "server is disabled until lab mode is turned off."
            )

    body = ProvisionServerResponse(
        accepted=False,
        status="not_implemented",
        namespace=namespace,
        helm_ready=False,
        message=(
            "Helm install is not implemented in this control plane. "
            "Charts live in deploy/helm/ (another workstream). This request was "
            "validated and is safe for a one-tenant lab (1 replica, namespace "
            f"{namespace})."
        ),
        request=request.model_dump(),
        next_steps=[
            "Wait for the OpenMU Helm chart in deploy/helm/.",
            f"helm install will target namespace {namespace} only.",
            "Values: server name, connect/game/chat/admin ports, PostgreSQL credentials, replicas=1.",
            "Do not run helm against kube-system or additional namespaces while SAAS_LAB_MODE=true.",
        ],
    )
    return JSONResponse(status_code=501, content=body.model_dump())


def _guard_ns(namespace: str) -> None:
    """Game-param routes do not require a live cluster, but still respect lab scope."""
    if settings.lab_mode and namespace != settings.lab_namespace:
        raise LabGuard(
            f"Lab mode only allows tenant namespace {settings.lab_namespace!r} "
            f"(got {namespace!r})."
        )


@app.get("/")
def root() -> dict:
    return {
        "service": settings.api_title,
        "docs": "/docs",
        "health": "/api/health",
        "lab_mode": settings.lab_mode,
        "lab_namespace": settings.lab_namespace,
    }
