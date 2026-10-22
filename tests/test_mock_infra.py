import pytest
from mock_infra.environment import MockEnvironment
from mock_infra.scenarios import inject_scenario, SCENARIOS
from mock_infra.models import ServiceStatus


def test_mock_environment_initialization():
    env = MockEnvironment()
    env.reset_to_baseline()
    assert len(env.services) == 5
    assert env.services["web-api"].status == ServiceStatus.HEALTHY
    assert env.services["postgres-db"].is_protected_tier1 is True


def test_inject_scenario_memory_leak():
    env = MockEnvironment()
    alert = inject_scenario(env, "INC-001")
    assert alert.service == "web-api"
    assert env.services["web-api"].status == ServiceStatus.CRITICAL
    assert env.services["web-api"].memory_mb > 900

    # Test remediation
    res = env.restart_service("web-api")
    assert res.success is True
    assert env.is_service_recovered("web-api") is True


def test_inject_scenario_bad_deployment():
    env = MockEnvironment()
    alert = inject_scenario(env, "INC-002")
    assert alert.service == "web-api"
    assert env.services["web-api"].active_version == "v2.4.1"

    # Attempting restart should FAIL to resolve bad deployment
    restart_res = env.restart_service("web-api")
    assert restart_res.success is False
    assert env.is_service_recovered("web-api") is False

    # Rollback should succeed and restore health
    rollback_res = env.rollback_deployment("web-api", "v2.3.9")
    assert rollback_res.success is True
    assert env.is_service_recovered("web-api") is True


def test_inject_scenario_upstream_outage():
    env = MockEnvironment()
    alert = inject_scenario(env, "INC-003")
    assert alert.service == "payment-gateway"

    # Neither restart nor rollback should fix upstream outage
    assert env.restart_service("payment-gateway").success is False
    assert env.rollback_deployment("payment-gateway").success is False


def test_inject_scenario_traffic_spike():
    env = MockEnvironment()
    alert = inject_scenario(env, "INC-006")
    assert alert.service == "web-api"
    assert env.services["web-api"].status == ServiceStatus.DEGRADED
    assert env.services["web-api"].cpu_percent > 90.0

    # Restart should NOT fix traffic spike
    restart_res = env.restart_service("web-api")
    # Scaling replicas SHOULD fix traffic spike
    scale_res = env.scale_replicas("web-api", 6)
    assert scale_res.success is True
    assert env.services["web-api"].replica_count == 6
    assert env.is_service_recovered("web-api") is True

