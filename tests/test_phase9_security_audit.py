import pytest
from app.services.audit_service import AuditLogService


@pytest.fixture
def temp_audit_service(tmp_path):
    audit_file = str(tmp_path / "test_audit_logs.csv")
    return AuditLogService(audit_file)


def test_audit_logging_and_retrieval(temp_audit_service):
    audit_svc = temp_audit_service

    # Log events
    audit_svc.log_event(
        candidate_id="CAN-AUDIT-001",
        actor="GAS_WEBHOOK",
        event_type="FORM_WEBHOOK_RECEIVED",
        details={"form_response_id": "RESP-100", "job_role": "PYTHON_DEV"}
    )

    audit_svc.log_event(
        candidate_id="CAN-AUDIT-001",
        actor="SYSTEM",
        event_type="DECISION_COMMITTED",
        details={"system_decision": "SHORTLISTED", "weighted_score": 91.0}
    )

    audit_svc.log_event(
        candidate_id="CAN-AUDIT-001",
        actor="HR_USER",
        event_type="HR_OVERRIDE_LOGGED",
        details={"override_decision": "REJECTED", "reason": "Role requirements updated."}
    )

    # Fetch audit trail
    trail = audit_svc.get_audit_trail("CAN-AUDIT-001")
    assert len(trail) == 3
    assert trail[0]["event_type"] == "FORM_WEBHOOK_RECEIVED"
    assert trail[1]["event_type"] == "DECISION_COMMITTED"
    assert trail[2]["event_type"] == "HR_OVERRIDE_LOGGED"
    assert trail[2]["actor"] == "HR_USER"
    assert trail[2]["details"]["override_decision"] == "REJECTED"
