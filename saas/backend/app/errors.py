"""Typed failures returned by the control plane."""

from __future__ import annotations

from fastapi import HTTPException, status


class ClusterUnavailable(HTTPException):
    def __init__(self, detail: str) -> None:
        super().__init__(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "cluster_unavailable",
                "error": detail,
                "hint": (
                    "This is a shared kubeadm lab. Set SAAS_KUBECONFIG to a "
                    "namespace-scoped kubeconfig (not admin.conf). Cluster-wide "
                    "list/watch is not used."
                ),
            },
        )


class LabGuard(HTTPException):
    def __init__(self, detail: str) -> None:
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "lab_guard",
                "error": detail,
                "hint": "SAAS_LAB_MODE=true allows a single tenant (SAAS_LAB_NAMESPACE) and 1 replica.",
            },
        )


class TenantNotFound(HTTPException):
    def __init__(self, namespace: str) -> None:
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "tenant_not_found", "error": f"Namespace {namespace!r} was not found."},
        )


class WorkloadNotFound(HTTPException):
    def __init__(self, kind: str, name: str, namespace: str) -> None:
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "workload_not_found",
                "error": f"{kind} {name!r} was not found in namespace {namespace!r}.",
            },
        )


class DatabaseUnavailable(HTTPException):
    def __init__(self, detail: str) -> None:
        super().__init__(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "database_unavailable",
                "error": detail,
                "required_env": [
                    "SAAS_PG_HOST",
                    "SAAS_PG_PORT",
                    "SAAS_PG_DATABASE",
                    "SAAS_PG_USER",
                    "SAAS_PG_PASSWORD",
                    "SAAS_PG_DSN (optional full URI)",
                    "SAAS_PG_DSN_<NAMESPACE> (optional per-tenant URI; hyphens become underscores)",
                ],
                "hint": (
                    "When a cluster is available, the API also looks for a postgres "
                    "Service/Secret in the tenant namespace (postgres, postgresql, "
                    "database, openmu-db)."
                ),
            },
        )
