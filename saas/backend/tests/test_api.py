from fastapi.testclient import TestClient

from app.main import app
from app.settings import get_settings


client = TestClient(app)


def test_health_reports_disconnected_cluster() -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["kubernetes"]["connected"] is False
    assert body["kubernetes"]["lab_mode"] is True
    assert body["kubernetes"]["lab_namespace"] == "openmu-lab"
    assert body["kubernetes"]["api_server"] == "https://api.test-01.k8s.t-h.cloud:6443"
    assert body["kubernetes"]["kubeconfig_path"] is None
    assert "SAAS_KUBECONFIG" in (body["kubernetes"]["error"] or "")
    assert "SAAS_PG_HOST" in (body["database"]["error"] or "")


def test_list_tenants_without_cluster() -> None:
    response = client.get("/api/tenants")
    assert response.status_code == 200
    body = response.json()
    assert body["cluster_connected"] is False
    assert body["tenants"] == []
    assert body["lab_mode"] is True


def test_restart_without_cluster_is_503() -> None:
    response = client.post("/api/tenants/openmu-lab/deployments/gameserver/restart")
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "cluster_unavailable"


def test_restart_foreign_namespace_blocked() -> None:
    response = client.post("/api/tenants/kube-system/pods/coredns/restart")
    assert response.status_code in {409, 503}
    detail = response.json()["detail"]
    assert detail["code"] in {"lab_guard", "cluster_unavailable"}


def test_game_rates_defaults_without_database() -> None:
    response = client.get("/api/tenants/openmu-lab/game/rates")
    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "defaults"
    assert body["experience_rate"] == 1.0
    assert body["persisted"] is False
    assert "SAAS_PG_HOST" in body["database_error"]


def test_game_rates_wrong_namespace_blocked() -> None:
    response = client.get("/api/tenants/someone-else/game/rates")
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "lab_guard"


def test_provision_validates_and_returns_501() -> None:
    response = client.post(
        "/api/servers",
        json={
            "server_name": "openmu-lab",
            "ports": {"connect": 44405, "game": 55901, "chat": 55980, "admin": 8080},
            "database": {
                "name": "openmu",
                "user": "postgres",
                "password": "lab-pass",
            },
            "replicas": 1,
        },
    )
    assert response.status_code == 501
    body = response.json()
    assert body["accepted"] is False
    assert body["status"] == "not_implemented"
    assert body["namespace"] == "openmu-lab"
    assert body["helm_ready"] is False
    assert body["request"]["replicas"] == 1


def test_provision_rejects_extra_replicas() -> None:
    response = client.post(
        "/api/servers",
        json={
            "server_name": "farm-2",
            "database": {"password": "lab-pass"},
            "replicas": 3,
        },
    )
    assert response.status_code == 422


def test_settings_lab_defaults() -> None:
    settings = get_settings()
    assert settings.lab_mode is True
    assert settings.lab_namespace == "openmu-lab"
    assert settings.max_tenants == 1
    assert settings.k8s_api_server == "https://api.test-01.k8s.t-h.cloud:6443"
    assert settings.kubeconfig is None


def test_explicit_missing_kubeconfig_path() -> None:
    from app.cluster import Cluster
    from app.settings import Settings

    cluster = Cluster(Settings.model_validate({"kubeconfig": "/tmp/openmu-lab-missing.kubeconfig"}))
    assert cluster.connected is False
    assert cluster.kubeconfig_path == "/tmp/openmu-lab-missing.kubeconfig"
    assert "not found" in (cluster.error or "").lower()


def test_client_stays_namespace_scoped() -> None:
    import inspect

    from app import cluster as cluster_mod

    source = inspect.getsource(cluster_mod)
    assert "list_namespace(" not in source
    assert "list_node(" not in source
    assert "read_namespace(" not in source
