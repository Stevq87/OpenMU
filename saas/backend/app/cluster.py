"""Namespace-scoped Kubernetes helpers for a shared kubeadm lab.

The client loads credentials only from SAAS_KUBECONFIG / KUBECONFIG (a
filesystem path). It never reads /etc/kubernetes/admin.conf, never lists
nodes or all namespaces, and never mutates kube-system. SSH is not used.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

from kubernetes import client, config
from kubernetes.client.exceptions import ApiException
from kubernetes.config.config_exception import ConfigException

from app.errors import ClusterUnavailable, LabGuard, WorkloadNotFound
from app.models import DeploymentInfo, EndpointInfo, PodInfo, PodLifecycle, TenantDetail, TenantSummary
from app.settings import Settings, get_settings

LOGGER = logging.getLogger(__name__)

OPENMU_NAME_HINTS = (
    "openmu",
    "gameserver",
    "game-server",
    "connectserver",
    "connect-server",
    "chatserver",
    "chat-server",
    "postgres",
    "postgresql",
)

SYSTEM_NAMESPACES = frozenset(
    {
        "kube-system",
        "kube-public",
        "kube-node-lease",
        "local-path-storage",
        "ingress-nginx",
        "calico-system",
        "tigera-operator",
        "default",
    }
)


class Cluster:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._core: client.CoreV1Api | None = None
        self._apps: client.AppsV1Api | None = None
        self.mode: str | None = None
        self.error: str | None = None
        self.kubeconfig_path: str | None = None
        self.active_api_server: str | None = None
        self._load()

    @property
    def connected(self) -> bool:
        return self._core is not None

    def resolve_kubeconfig_path(self) -> str | None:
        """Only the env path (SAAS_KUBECONFIG or KUBECONFIG). Never embed file contents."""
        explicit = self.settings.kubeconfig
        return os.path.expanduser(explicit) if explicit else None

    def _load(self) -> None:
        path = self.resolve_kubeconfig_path()
        self.kubeconfig_path = path
        try:
            if path:
                if not os.path.isfile(path):
                    self.error = (
                        f"Kubeconfig not found at {path}. "
                        f"Create a local file pointing at {self.settings.k8s_api_server} "
                        "(do not commit it)."
                    )
                    return
                kwargs: dict[str, Any] = {"config_file": path}
                if self.settings.kube_context:
                    kwargs["context"] = self.settings.kube_context
                config.load_kube_config(**kwargs)
                self.mode = "kubeconfig"
                self._apply_lab_sni()
            else:
                try:
                    config.load_incluster_config()
                    self.mode = "in-cluster"
                except ConfigException:
                    self.error = (
                        "No Kubernetes credentials. Set SAAS_KUBECONFIG (or KUBECONFIG) "
                        f"to a namespace-scoped kubeconfig for {self.settings.lab_namespace} "
                        f"whose cluster.server is {self.settings.k8s_api_server}. "
                        "Do not put tokens, client certs, or SSH keys in git. "
                        "admin.conf on the CP is not readable without sudo."
                    )
                    LOGGER.info("Kubernetes client not configured: %s", self.error)
                    return
        except Exception as exc:  # noqa: BLE001 — surface any kubeconfig failure
            self.error = (
                f"Failed to load kubeconfig ({exc}). "
                f"Expected lab API {self.settings.k8s_api_server}."
            )
            LOGGER.info("Kubernetes client not configured: %s", exc)
            return
        try:
            self._core = client.CoreV1Api()
            self._apps = client.AppsV1Api()
            self.active_api_server = client.Configuration.get_default_copy().host or None
        except Exception as exc:  # noqa: BLE001
            self.error = str(exc)
            self._core = None
            self._apps = None

    def _apply_lab_sni(self) -> None:
        """config.ip talks to the CP IP; the cert is for api.test-01.k8s.t-h.cloud."""
        configuration = client.Configuration.get_default_copy()
        if configuration.tls_server_name:
            return
        if self.settings.k8s_tls_server_name:
            configuration.tls_server_name = self.settings.k8s_tls_server_name
            client.Configuration.set_default(configuration)

    def require(self) -> tuple[client.CoreV1Api, client.AppsV1Api]:
        if self._core is None or self._apps is None:
            raise ClusterUnavailable(self.error or "Kubernetes client is not configured.")
        return self._core, self._apps

    def assert_namespace_allowed(self, namespace: str) -> None:
        if namespace in SYSTEM_NAMESPACES:
            raise LabGuard(f"Refusing to touch system namespace {namespace!r}.")
        if self.settings.lab_mode and namespace != self.settings.lab_namespace:
            raise LabGuard(
                f"Lab mode only allows tenant namespace {self.settings.lab_namespace!r} "
                f"(got {namespace!r})."
            )

    def namespace_for_server_name(self, server_name: str) -> str:
        if self.settings.lab_mode:
            return self.settings.lab_namespace
        if server_name.startswith("openmu-"):
            return server_name
        return f"openmu-{server_name}"

    def list_tenants(self) -> list[TenantSummary]:
        # Shared kubeadm lab: never list Namespace objects cluster-wide.
        self.require()
        return [self._summarize_namespace(self.settings.lab_namespace, missing_ok=True)]

    def get_tenant(self, namespace: str) -> TenantDetail:
        self.assert_namespace_allowed(namespace)
        self.require()
        pods = self.list_pods(namespace)
        deployments = self.list_deployments(namespace)
        endpoints = self.list_endpoints(namespace)
        return TenantDetail(
            namespace=namespace,
            display_name=namespace,
            status=_aggregate_status(pods),
            pod_count=len(pods),
            is_lab_default=namespace == self.settings.lab_namespace,
            endpoints=endpoints,
            cluster_connected=True,
            pods=pods,
            deployments=deployments,
        )

    def _summarize_namespace(self, namespace: str, *, missing_ok: bool) -> TenantSummary:
        try:
            pods = self.list_pods(namespace)
            endpoints = self.list_endpoints(namespace)
            status = _aggregate_status(pods) if pods else "Stopped"
            return TenantSummary(
                namespace=namespace,
                display_name=namespace,
                status=status,
                pod_count=len(pods),
                is_lab_default=namespace == self.settings.lab_namespace,
                endpoints=endpoints,
            )
        except ApiException as exc:
            if missing_ok and exc.status == 404:
                return TenantSummary(
                    namespace=namespace,
                    display_name=namespace,
                    status="Stopped",
                    pod_count=0,
                    is_lab_default=namespace == self.settings.lab_namespace,
                    endpoints=[],
                )
            raise ClusterUnavailable(f"Failed to list objects in {namespace}: {exc.reason}") from exc

    def list_pods(self, namespace: str) -> list[PodInfo]:
        self.assert_namespace_allowed(namespace)
        core, _ = self.require()
        try:
            items = core.list_namespaced_pod(namespace).items
        except ApiException as exc:
            _raise_ns_error("pods", namespace, exc)
            return []
        pods = [_pod_info(pod) for pod in items if _is_openmu_object(pod.metadata)]
        if not pods and items:
            # Empty filter: still show namespace pods so a lab install with
            # unexpected labels is visible.
            pods = [_pod_info(pod) for pod in items]
        return pods

    def get_pod(self, namespace: str, name: str) -> PodInfo:
        self.assert_namespace_allowed(namespace)
        core, _ = self.require()
        try:
            pod = core.read_namespaced_pod(name, namespace)
        except ApiException as exc:
            if exc.status == 404:
                raise WorkloadNotFound("Pod", name, namespace) from exc
            _raise_ns_error("pod", namespace, exc)
            raise ClusterUnavailable(f"Failed to read pod {name}: {exc.reason}") from exc
        return _pod_info(pod)

    def list_deployments(self, namespace: str) -> list[DeploymentInfo]:
        self.assert_namespace_allowed(namespace)
        _, apps = self.require()
        try:
            items = apps.list_namespaced_deployment(namespace).items
        except ApiException as exc:
            _raise_ns_error("deployments", namespace, exc)
            return []
        return [
            DeploymentInfo(
                name=d.metadata.name,
                namespace=namespace,
                replicas=d.spec.replicas or 0,
                ready_replicas=d.status.ready_replicas or 0,
                component=_component(d.metadata),
            )
            for d in items
        ]

    def list_endpoints(self, namespace: str) -> list[EndpointInfo]:
        self.assert_namespace_allowed(namespace)
        core, _ = self.require()
        try:
            services = core.list_namespaced_service(namespace).items
        except ApiException as exc:
            _raise_ns_error("services", namespace, exc)
            return []

        node_ip = self.settings.k8s_node_ip
        endpoints: list[EndpointInfo] = []
        for svc in services:
            if not _is_openmu_object(svc.metadata) and services:
                pass
            ip, note = _service_ip(svc, node_ip)
            for port in svc.spec.ports or []:
                endpoints.append(
                    EndpointInfo(
                        name=svc.metadata.name,
                        namespace=namespace,
                        service_type=svc.spec.type or "ClusterIP",
                        ip=ip,
                        port=port.port,
                        node_port=port.node_port,
                        protocol=port.protocol or "TCP",
                        component=_component(svc.metadata) or port.name,
                        note=note,
                    )
                )
        return endpoints

    def restart_pod(self, namespace: str, name: str) -> None:
        self.assert_namespace_allowed(namespace)
        core, _ = self.require()
        try:
            core.delete_namespaced_pod(name, namespace)
        except ApiException as exc:
            if exc.status == 404:
                raise WorkloadNotFound("Pod", name, namespace) from exc
            _raise_ns_error("pod", namespace, exc)
            raise ClusterUnavailable(f"Failed to restart pod {name}: {exc.reason}") from exc

    def restart_deployment(self, namespace: str, name: str) -> None:
        self.assert_namespace_allowed(namespace)
        _, apps = self.require()
        stamp = datetime.now(timezone.utc).isoformat()
        body = {
            "spec": {
                "template": {
                    "metadata": {
                        "annotations": {"kubectl.kubernetes.io/restartedAt": stamp}
                    }
                }
            }
        }
        try:
            apps.patch_namespaced_deployment(name, namespace, body)
        except ApiException as exc:
            if exc.status == 404:
                raise WorkloadNotFound("Deployment", name, namespace) from exc
            _raise_ns_error("deployment", namespace, exc)
            raise ClusterUnavailable(f"Failed to restart deployment {name}: {exc.reason}") from exc

    def existing_tenant_count(self) -> int:
        """Used by provision to refuse a second lab tenant."""
        try:
            tenants = self.list_tenants()
        except ClusterUnavailable:
            return 0
        return sum(1 for t in tenants if t.pod_count > 0 or t.status != "Stopped")

    def discover_postgres(self, namespace: str) -> dict[str, str] | None:
        """Best-effort Service/Secret lookup in the tenant namespace only."""
        if not self.connected:
            return None
        try:
            self.assert_namespace_allowed(namespace)
        except LabGuard:
            return None
        core = self._core
        if core is None:
            return None
        found: dict[str, str] = {}
        try:
            for secret_name in ("openmu-db", "postgres", "postgresql"):
                try:
                    secret = core.read_namespaced_secret(secret_name, namespace)
                except ApiException:
                    continue
                data = secret.data or {}
                found.update(_decode_secret(data))
                break
            for svc_name in ("postgres", "postgresql", "database", "openmu-db"):
                try:
                    svc = core.read_namespaced_service(svc_name, namespace)
                except ApiException:
                    continue
                found.setdefault("host", f"{svc.metadata.name}.{namespace}.svc")
                ports = svc.spec.ports or []
                if ports:
                    found.setdefault("port", str(ports[0].port))
                break
        except ApiException as exc:
            LOGGER.info("Postgres discovery in %s failed: %s", namespace, exc.reason)
        return found or None


def _raise_ns_error(kind: str, namespace: str, exc: ApiException) -> None:
    if exc.status == 404:
        return
    if exc.status in {401, 403}:
        raise ClusterUnavailable(
            f"Access denied listing {kind} in {namespace} ({exc.reason}). "
            "Use a namespace-scoped kubeconfig for this shared kubeadm lab; "
            "cluster-admin / list-nodes / list-namespaces is not required and not used."
        ) from exc
    raise ClusterUnavailable(f"Failed to access {kind} in {namespace}: {exc.reason}") from exc


def _is_openmu_object(metadata: Any) -> bool:
    labels = (metadata.labels or {}) if metadata else {}
    if labels.get("app.kubernetes.io/part-of") == "openmu":
        return True
    if labels.get("openmu.saas/component"):
        return True
    blob = " ".join(
        [
            getattr(metadata, "name", "") or "",
            labels.get("app", ""),
            labels.get("app.kubernetes.io/name", ""),
            labels.get("app.kubernetes.io/component", ""),
        ]
    ).lower()
    return any(hint in blob for hint in OPENMU_NAME_HINTS)


def _component(metadata: Any) -> str | None:
    labels = (metadata.labels or {}) if metadata else {}
    return (
        labels.get("openmu.saas/component")
        or labels.get("app.kubernetes.io/component")
        or labels.get("app.kubernetes.io/name")
        or labels.get("app")
    )


def _pod_info(pod: Any) -> PodInfo:
    statuses = pod.status.container_statuses or []
    restarts = sum(cs.restart_count or 0 for cs in statuses)
    reasons = []
    ready = bool(statuses) and all(cs.ready for cs in statuses)
    for cs in statuses:
        waiting = getattr(cs.state, "waiting", None)
        terminated = getattr(cs.state, "terminated", None)
        if waiting and waiting.reason:
            reasons.append(waiting.reason)
        if terminated and terminated.reason:
            reasons.append(terminated.reason)
    status = _classify(pod.status.phase, reasons, ready, replicas_zero=False)
    owner = None
    for ref in pod.metadata.owner_references or []:
        if ref.kind in {"ReplicaSet", "StatefulSet"}:
            owner = ref.name.rsplit("-", 1)[0] if ref.kind == "ReplicaSet" else ref.name
            break
    return PodInfo(
        name=pod.metadata.name,
        namespace=pod.metadata.namespace,
        status=status,
        phase=pod.status.phase,
        ready=ready,
        restarts=restarts,
        node=pod.spec.node_name,
        deployment=owner,
        component=_component(pod.metadata),
        reason=reasons[0] if reasons else None,
    )


def _classify(phase: str | None, reasons: list[str], ready: bool, replicas_zero: bool) -> PodLifecycle:
    crash_reasons = {"CrashLoopBackOff", "Error", "OOMKilled", "ImagePullBackOff"}
    if any(r in crash_reasons for r in reasons) or phase == "Failed":
        return "Crash"
    if replicas_zero or phase == "Succeeded":
        return "Stopped"
    if phase == "Pending":
        return "Pending"
    if phase == "Running":
        return "Running" if ready else "Starting"
    return "Unknown"


def _aggregate_status(pods: list[PodInfo]) -> PodLifecycle:
    if not pods:
        return "Stopped"
    order: tuple[PodLifecycle, ...] = ("Crash", "Pending", "Starting", "Running", "Stopped", "Unknown")
    statuses = {p.status for p in pods}
    for candidate in order:
        if candidate in statuses:
            return candidate
    return "Unknown"


def _service_ip(svc: Any, node_ip: str | None) -> tuple[str | None, str | None]:
    spec_type = svc.spec.type or "ClusterIP"
    if spec_type == "LoadBalancer":
        ingress = (svc.status.load_balancer.ingress or []) if svc.status.load_balancer else []
        if ingress:
            return ingress[0].ip or ingress[0].hostname, None
        return svc.spec.cluster_ip, "LoadBalancer pending an external address"
    if spec_type == "NodePort":
        return node_ip or svc.spec.cluster_ip, (
            "NodePort — set SAAS_K8S_NODE_IP to a worker address; nodes are not listed"
            if not node_ip
            else None
        )
    return svc.spec.cluster_ip, "ClusterIP (internal to the lab cluster)"


def _decode_secret(data: dict[str, str]) -> dict[str, str]:
    import base64

    decoded: dict[str, str] = {}
    mapping = {
        "host": "host",
        "hostname": "host",
        "port": "port",
        "database": "database",
        "dbname": "database",
        "postgres-database": "database",
        "username": "user",
        "user": "user",
        "postgres-user": "user",
        "password": "password",
        "postgres-password": "password",
        "POSTGRES_PASSWORD": "password",
    }
    for raw_key, value in data.items():
        try:
            text = base64.b64decode(value).decode("utf-8")
        except Exception:  # noqa: BLE001
            text = value
        mapped = mapping.get(raw_key) or mapping.get(raw_key.lower())
        if mapped:
            decoded[mapped] = text
    return decoded
