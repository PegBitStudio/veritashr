"""Human-in-the-loop governance: every decision is attributed, reasoned and tamper-evident."""

import json
import pytest
from src.governance.audit_log import AuditLog
from src.models.issue import QualityIssue, IssueCategory, Severity, EvidenceItem

def make_issue(i=1):
    return QualityIssue(
        issue_id=f"ERR-T-{i}", category=IssueCategory.GHOST_RECORD, severity=Severity.CRITICAL, title="t",
        description="d", primary_entity_id=f"EK{i}", entity_name="n", source_systems=["payroll"],
        fields_in_conflict=["pay_status"], evidence_trail=[EvidenceItem("payroll", "pay_status", "ACTIVE")],
        suggested_fix="f", recommended_target_system="payroll", recommended_target_field="pay_status",
        recommended_target_value="INACTIVE", confidence_score=0.99, rationale="r", impact_score=90)

def test_decisions_are_chained_and_verifiable(tmp_path):
    log = AuditLog(str(tmp_path / "audit.jsonl"))
    a, b = make_issue(1), make_issue(2)
    log.record(a, "APPROVE", "steward.one")
    log.record(b, "MODIFY", "steward.two", "use HOLD pending recovery", final_value="HOLD")
    ok, _ = log.verify()
    assert ok and a.approval_status == "APPROVED" and b.approval_status == "MODIFIED"
    e = log.entries()
    assert e[0]["current_value"] == "ACTIVE" and e[1]["final_value"] == "HOLD" and e[1]["prev_hash"] == e[0]["hash"]

def test_tampering_is_detected(tmp_path):
    path = tmp_path / "audit.jsonl"
    log = AuditLog(str(path))
    log.record(make_issue(1), "APPROVE", "steward.one")
    log.record(make_issue(2), "APPROVE", "steward.one")
    lines = path.read_text().splitlines()
    rec = json.loads(lines[0]); rec["reviewer"] = "someone.else"
    path.write_text(json.dumps(rec) + "\n" + lines[1] + "\n")
    ok, msg = log.verify()
    assert not ok

def test_guardrails(tmp_path):
    log = AuditLog(str(tmp_path / "audit.jsonl"))
    with pytest.raises(ValueError):
        log.record(make_issue(), "APPROVE", "")
    with pytest.raises(ValueError):
        log.record(make_issue(), "REJECT", "steward.one", "")
    with pytest.raises(ValueError):
        log.record(make_issue(), "MODIFY", "steward.one", "x", final_value="")

def test_change_set_export_only_contains_approved(tmp_path):
    log = AuditLog(str(tmp_path / "audit.jsonl"))
    log.record(make_issue(1), "APPROVE", "s")
    log.record(make_issue(2), "REJECT", "s", "false positive: on secondment")
    assert log.export_change_set(str(tmp_path / "changes.csv")) == 1
