import os
import pytest
from escalation.handoff import EscalationReport
from escalation.notifier import EscalationNotifier


@pytest.fixture
def sample_report():
    return EscalationReport(
        incident_id="ALT-9004",
        target_service="postgres-db",
        escalation_reason="VETO: 'postgres-db' is classified as Tier-1 protected infrastructure.",
        severity="CRITICAL",
        diagnosed_hypothesis="Database connection pool exhausted.",
        confidence_score=0.60,
        actions_attempted=[],
        unresolved_symptoms=["Active connection count > 95% limit"],
        recommended_human_action="Increase connection pool size or inspect long-running transactions.",
        timestamp="2026-10-14 12:00:00",
    )


def test_format_slack_payload(sample_report):
    notifier = EscalationNotifier()
    payload = notifier.format_slack_payload(sample_report)

    assert "blocks" in payload
    assert len(payload["blocks"]) >= 5
    assert "postgres-db" in payload["text"]
    assert "ALT-9004" in payload["text"]


def test_save_to_audit_file(sample_report, tmp_path):
    log_file = tmp_path / "test_escalations.log"
    notifier = EscalationNotifier()

    saved_path = notifier.save_to_audit_file(sample_report, filepath=str(log_file))
    assert os.path.exists(saved_path)

    with open(saved_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert "ALT-9004" in content
    assert "postgres-db" in content
    assert "Tier-1 protected" in content


def test_dispatch_console_and_audit(sample_report, tmp_path):
    log_file = tmp_path / "audit.log"
    notifier = EscalationNotifier()

    result = notifier.dispatch(sample_report, channel="console", audit_file=str(log_file))
    assert result["success"] is True
    assert os.path.exists(str(log_file))
