"""
Tamper-evident, append-only audit trail for steward decisions.

Every Approve / Modify / Reject is written as one JSON line that includes the SHA-256 hash of
the previous line, so any edit, deletion or reordering of history breaks the chain and is
detected by verify(). Nothing here writes to source HR systems: approved fixes are exported as
a change set that the system owner applies through their normal change process.
"""

import os
import csv
import json
import hashlib
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Tuple
from src.models.issue import ApprovalStatus

GENESIS = "0" * 64
ACTIONS = {"APPROVE": "APPROVED", "MODIFY": "MODIFIED", "REJECT": "REJECTED"}

def _digest(entry: Dict[str, Any]) -> str:
    body = {k: v for k, v in entry.items() if k != "hash"}
    return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()

class AuditLog:
    def __init__(self, path: str):
        self.path = path
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

    def entries(self) -> List[Dict[str, Any]]:
        if not os.path.exists(self.path):
            return []
        with open(self.path, "r", encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]

    def _last_hash(self) -> str:
        e = self.entries()
        return e[-1]["hash"] if e else GENESIS

    def record(self, issue, action: str, reviewer: str, comment: str = "",
               final_value: Optional[Any] = None) -> Dict[str, Any]:
        """Records one human decision on an issue. MODIFY requires a final value; REJECT requires a reason."""
        action = action.upper()
        if action not in ACTIONS:
            raise ValueError(f"Unknown action {action}")
        if not reviewer or not reviewer.strip():
            raise ValueError("A named reviewer is required for every decision")
        if action == "REJECT" and not comment.strip():
            raise ValueError("A reason is required to reject a suggested fix")
        if action == "MODIFY" and (final_value is None or str(final_value).strip() == ""):
            raise ValueError("A replacement value is required to modify a fix")

        current = next((ev.recorded_value for ev in issue.evidence_trail
                        if ev.system_name == issue.recommended_target_system and ev.field_name == issue.recommended_target_field), None)
        entry = {
            "seq": len(self.entries()) + 1,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "reviewer": reviewer.strip(),
            "action": action,
            "issue_id": issue.issue_id,
            "category": issue.category.value,
            "entity_id": issue.primary_entity_id,
            "target": f"{issue.recommended_target_system}.{issue.recommended_target_field}",
            "current_value": None if current is None else str(current),
            "suggested_value": str(issue.recommended_target_value),
            "final_value": None if action == "REJECT" else str(final_value if action == "MODIFY" else issue.recommended_target_value),
            "confidence": issue.confidence_score,
            "evidence_sha256": hashlib.sha256(json.dumps(
                [[e.system_name, e.field_name, str(e.recorded_value)] for e in issue.evidence_trail]).encode()).hexdigest(),
            "comment": comment.strip(),
            "prev_hash": self._last_hash(),
        }
        entry["hash"] = _digest(entry)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        issue.approval_status = ApprovalStatus(ACTIONS[action])
        issue.approved_by = entry["reviewer"]
        issue.reviewed_at = entry["timestamp_utc"]
        issue.reviewer_comments = entry["comment"] or None
        return entry

    def verify(self) -> Tuple[bool, str]:
        """Re-computes the hash chain; returns (ok, message)."""
        prev = GENESIS
        for i, e in enumerate(self.entries(), 1):
            if e.get("prev_hash") != prev:
                return False, f"Chain broken at entry {i}: previous-hash mismatch (history edited, removed or reordered)"
            if _digest(e) != e.get("hash"):
                return False, f"Entry {i} was altered after it was written"
            prev = e["hash"]
        return True, f"{len(self.entries())} entries verified, chain intact"

    def apply_to_issues(self, issues: List[Any]):
        """Restores the latest decision per issue (so the queue survives restarts)."""
        by_id = {i.issue_id: i for i in issues}
        for e in self.entries():
            i = by_id.get(e["issue_id"])
            if i:
                i.approval_status = ApprovalStatus(ACTIONS[e["action"]])
                i.approved_by, i.reviewed_at, i.reviewer_comments = e["reviewer"], e["timestamp_utc"], e["comment"] or None

    def export_change_set(self, out_path: str) -> int:
        """Writes the approved / modified fixes as a change request for system owners. Never touches live systems."""
        latest: Dict[str, Dict[str, Any]] = {}
        for e in self.entries():
            latest[e["issue_id"]] = e
        rows = [e for e in latest.values() if e["action"] in ("APPROVE", "MODIFY")]
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        cols = ["issue_id", "entity_id", "target", "current_value", "final_value", "reviewer", "timestamp_utc", "comment", "hash"]
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)
        return len(rows)
