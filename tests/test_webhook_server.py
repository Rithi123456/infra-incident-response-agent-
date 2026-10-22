import pytest
import json
from api.webhook_server import create_app


@pytest.fixture
def client():
    app = create_app(simulated=True, engine="raw")
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_index_dashboard(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Autonomous Infra/DevOps Incident-Response Agent" in response.get_data(as_text=True)


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "healthy"
    assert data["service"] == "infra-incident-response-agent"


def test_list_scenarios(client):
    response = client.get("/api/v1/scenarios")
    assert response.status_code == 200
    data = response.get_json()
    assert data["total"] == 6
    scenario_ids = [s["id"] for s in data["scenarios"]]
    assert "INC-001" in scenario_ids
    assert "INC-004" in scenario_ids
    assert "INC-006" in scenario_ids


def test_ingest_alert_scenario_resolved(client):
    payload = {"scenario_id": "INC-001"}
    response = client.post("/api/v1/alert", data=json.dumps(payload), content_type="application/json")
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "RESOLVED"
    assert data["service_recovered"] is True
    assert data["confidence_score"] > 0.5
    assert len(data["actions_attempted"]) >= 1


def test_ingest_alert_scenario_escalated(client):
    payload = {"scenario_id": "INC-004"}  # Tier-1 DB deadlock
    response = client.post("/api/v1/alert", data=json.dumps(payload), content_type="application/json")
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "ESCALATED"
    assert data["escalation_report"] is not None
    assert "postgres-db" in data["escalation_report"]["target_service"]


def test_ingest_alertmanager_format(client):
    alertmanager_payload = {
        "receiver": "infra-agent",
        "status": "firing",
        "alerts": [
            {
                "status": "firing",
                "labels": {
                    "alertname": "PodMemoryExhaustion",
                    "service": "web-api",
                    "severity": "critical",
                },
                "annotations": {
                    "summary": "Memory utilization at 96% limit",
                    "metric": "memory_mb",
                    "value": "980.0",
                    "threshold": "850.0",
                },
            }
        ],
    }
    response = client.post(
        "/api/v1/alert?simulated=true",
        data=json.dumps(alertmanager_payload),
        content_type="application/json",
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["target_service"] == "web-api"
    assert "status" in data


def test_cors_headers_and_preflight(client):
    # Test GET has CORS header
    res_get = client.get("/api/v1/scenarios")
    assert res_get.status_code == 200
    assert res_get.headers.get("Access-Control-Allow-Origin") == "*"

    # Test OPTIONS preflight
    res_opt = client.open("/api/v1/alert", method="OPTIONS")
    assert res_opt.status_code in (200, 204)
    assert res_opt.headers.get("Access-Control-Allow-Origin") == "*"
