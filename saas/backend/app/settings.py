"""Runtime configuration for the SaaS control plane.

Sized for a one-tenant Kubernetes lab: a single FastAPI process, no
cluster-wide farms, and no assumed kubeconfig until the coordinator
wires credentials.
"""

from __future__ import annotations

import os
from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Public lab API only — never a credential. Auth stays in a local kubeconfig file.
DEFAULT_LAB_API_SERVER = "https://api.test-01.k8s.t-h.cloud:6443"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    api_title: str = "OpenMU SaaS Control Plane"
    api_prefix: str = "/api"
    cors_origins: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173",
        description="Comma-separated browser origins allowed to call the API.",
    )

    kubeconfig: str | None = Field(
        default=None,
        validation_alias=AliasChoices("SAAS_KUBECONFIG", "KUBECONFIG"),
        description="Filesystem path to a kubeconfig. Do not commit that file.",
    )
    kube_context: str | None = Field(
        default=None,
        validation_alias=AliasChoices("SAAS_KUBE_CONTEXT", "KUBE_CONTEXT"),
    )
    k8s_api_server: str = Field(
        default=DEFAULT_LAB_API_SERVER,
        validation_alias="SAAS_K8S_API_SERVER",
        description="Lab Kubernetes API URL (host:6443). Used as the intended cluster; auth is not in git.",
    )
    k8s_node_ip: str | None = Field(
        default=None,
        validation_alias="SAAS_K8S_NODE_IP",
        description="Optional worker IP for NodePort display. Nodes are never listed (shared kubeadm RBAC).",
    )

    lab_mode: bool = Field(
        default=True,
        validation_alias="SAAS_LAB_MODE",
        description="Cap the control plane to a single lab tenant and 1 replica.",
    )
    lab_namespace: str = Field(
        default="openmu-lab",
        validation_alias="SAAS_LAB_NAMESPACE",
        description="Default (and, in lab mode, only) tenant namespace.",
    )
    max_tenants: int = Field(default=1, validation_alias="SAAS_MAX_TENANTS")
    tenant_label: str = Field(
        default="openmu.saas/tenant",
        description="Namespace label key that marks an OpenMU tenant.",
    )

    pg_host: str | None = Field(default=None, validation_alias="SAAS_PG_HOST")
    pg_port: int = Field(default=5432, validation_alias="SAAS_PG_PORT")
    pg_database: str = Field(default="openmu", validation_alias="SAAS_PG_DATABASE")
    pg_user: str = Field(default="postgres", validation_alias="SAAS_PG_USER")
    pg_password: str | None = Field(default=None, validation_alias="SAAS_PG_PASSWORD")
    pg_sslmode: str = Field(default="prefer", validation_alias="SAAS_PG_SSLMODE")
    pg_dsn: str | None = Field(
        default=None,
        validation_alias="SAAS_PG_DSN",
        description="Full DSN used when per-tenant discovery finds nothing.",
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    def pg_dsn_for_namespace(self, namespace: str) -> str | None:
        key = "SAAS_PG_DSN_" + namespace.upper().replace("-", "_")
        return os.environ.get(key) or self.pg_dsn

    def pg_configured(self) -> bool:
        return bool(self.pg_dsn or self.pg_host)


@lru_cache
def get_settings() -> Settings:
    return Settings()
