"""Request and response models for the lab control plane."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


PodLifecycle = Literal["Running", "Stopped", "Crash", "Pending", "Starting", "Unknown"]


class ClusterHealth(BaseModel):
    connected: bool
    mode: str | None = None
    error: str | None = None
    lab_mode: bool = True
    lab_namespace: str = "openmu-lab"
    api_server: str
    kubeconfig_path: str | None = None


class DatabaseHealth(BaseModel):
    configured: bool
    host: str | None = None
    port: int | None = None
    database: str | None = None
    user: str | None = None
    error: str | None = None


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    kubernetes: ClusterHealth
    database: DatabaseHealth


class EndpointInfo(BaseModel):
    name: str
    namespace: str
    service_type: str
    ip: str | None = None
    port: int | None = None
    node_port: int | None = None
    protocol: str = "TCP"
    component: str | None = None
    note: str | None = None


class PodInfo(BaseModel):
    name: str
    namespace: str
    status: PodLifecycle
    phase: str | None = None
    ready: bool = False
    restarts: int = 0
    node: str | None = None
    deployment: str | None = None
    component: str | None = None
    reason: str | None = None


class DeploymentInfo(BaseModel):
    name: str
    namespace: str
    replicas: int = 0
    ready_replicas: int = 0
    component: str | None = None


class TenantSummary(BaseModel):
    namespace: str
    display_name: str
    status: PodLifecycle
    pod_count: int = 0
    is_lab_default: bool = False
    endpoints: list[EndpointInfo] = Field(default_factory=list)


class TenantDetail(TenantSummary):
    cluster_connected: bool = True
    pods: list[PodInfo] = Field(default_factory=list)
    deployments: list[DeploymentInfo] = Field(default_factory=list)


class TenantListResponse(BaseModel):
    cluster_connected: bool
    cluster_error: str | None = None
    lab_mode: bool = True
    lab_namespace: str
    tenants: list[TenantSummary]


class RestartRequest(BaseModel):
    """Optional body; restart always targets one named object in one namespace."""

    reason: str | None = Field(default=None, max_length=200)


class RestartResponse(BaseModel):
    namespace: str
    kind: Literal["Pod", "Deployment"]
    name: str
    action: str
    message: str


class GameRates(BaseModel):
    experience_rate: float = Field(default=1.0, ge=0.1, le=10_000)
    master_experience_rate: float = Field(default=1.0, ge=0.1, le=10_000)
    maximum_item_option_level_drop: int = Field(default=4, ge=0, le=15)
    excellent_item_drop_level_delta: int = Field(default=25, ge=0, le=255)
    should_drop_money: bool = True
    item_drop_duration_seconds: int = Field(default=60, ge=1, le=3600)
    source: Literal["postgresql", "defaults"] = "defaults"
    persisted: bool = False
    database_error: str | None = None


class DropGroup(BaseModel):
    id: str
    description: str | None = None
    chance: float = Field(ge=0.0, le=1.0)
    minimum_monster_level: int | None = None
    maximum_monster_level: int | None = None
    item_type: int | None = None


class DropGroupUpdate(BaseModel):
    chance: float = Field(ge=0.0, le=1.0)
    minimum_monster_level: int | None = Field(default=None, ge=0, le=255)
    maximum_monster_level: int | None = Field(default=None, ge=0, le=255)


class DropListResponse(BaseModel):
    items: list[DropGroup] = Field(default_factory=list)
    source: Literal["postgresql", "defaults"] = "defaults"
    database_error: str | None = None


class SpawnArea(BaseModel):
    id: str
    monster: str | None = None
    map: str | None = None
    quantity: int = Field(ge=0, le=10_000)
    x1: int = Field(ge=0, le=255)
    y1: int = Field(ge=0, le=255)
    x2: int = Field(ge=0, le=255)
    y2: int = Field(ge=0, le=255)


class SpawnUpdate(BaseModel):
    quantity: int = Field(ge=0, le=500)
    x1: int | None = Field(default=None, ge=0, le=255)
    y1: int | None = Field(default=None, ge=0, le=255)
    x2: int | None = Field(default=None, ge=0, le=255)
    y2: int | None = Field(default=None, ge=0, le=255)


class SpawnListResponse(BaseModel):
    items: list[SpawnArea] = Field(default_factory=list)
    source: Literal["postgresql", "defaults"] = "defaults"
    database_error: str | None = None


class GameEvent(BaseModel):
    id: str
    name: str | None = None
    game_level: int | None = None
    entrance_fee: int = 0
    maximum_player_count: int = 0
    minimum_character_level: int = 0
    maximum_character_level: int = 0
    allow_party: bool = True


class EventUpdate(BaseModel):
    entrance_fee: int | None = Field(default=None, ge=0)
    maximum_player_count: int | None = Field(default=None, ge=1, le=500)
    minimum_character_level: int | None = Field(default=None, ge=0, le=400)
    maximum_character_level: int | None = Field(default=None, ge=0, le=400)
    allow_party: bool | None = None


class EventListResponse(BaseModel):
    items: list[GameEvent] = Field(default_factory=list)
    source: Literal["postgresql", "defaults"] = "defaults"
    database_error: str | None = None


class ProvisionPorts(BaseModel):
    connect: int = Field(default=44405, ge=1024, le=65535)
    game: int = Field(default=55901, ge=1024, le=65535)
    chat: int = Field(default=55980, ge=1024, le=65535)
    admin: int = Field(default=8080, ge=1024, le=65535)


class ProvisionDatabase(BaseModel):
    host: str | None = Field(
        default=None,
        description="Leave empty to let Helm create in-cluster PostgreSQL for the tenant.",
    )
    name: str = Field(default="openmu", min_length=1, max_length=63)
    user: str = Field(default="postgres", min_length=1, max_length=63)
    password: str = Field(min_length=4, max_length=128)


class ProvisionServerRequest(BaseModel):
    """Values the Helm workstream will consume. Lab mode forces 1 replica."""

    server_name: str = Field(
        min_length=2,
        max_length=40,
        description="Tenant id; becomes the Kubernetes namespace (openmu-<name> if no prefix).",
    )
    display_name: str | None = Field(default=None, max_length=80)
    ports: ProvisionPorts = Field(default_factory=ProvisionPorts)
    database: ProvisionDatabase
    replicas: int = Field(default=1, ge=1, le=1, description="Lab default: 1 replica per component.")

    @field_validator("server_name")
    @classmethod
    def dns_label(cls, value: str) -> str:
        cleaned = value.strip().lower().replace("_", "-")
        if not cleaned.replace("-", "").isalnum():
            raise ValueError("server_name must be a DNS label (letters, digits, hyphen).")
        if cleaned.startswith("-") or cleaned.endswith("-"):
            raise ValueError("server_name cannot start or end with a hyphen.")
        return cleaned


class ProvisionServerResponse(BaseModel):
    accepted: bool
    status: Literal["not_implemented", "rejected"]
    namespace: str | None = None
    message: str
    helm_ready: bool = False
    request: dict[str, Any]
    next_steps: list[str] = Field(default_factory=list)
