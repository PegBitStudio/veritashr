"""
Data Trust Scoring Engine for VeritasHR.

Every score is a plain share an executive can verify:
  trust(report) = % of employee records whose fields used by that report have no open issue
  trust(field)  = % of employee records with no open issue on that field
  trust(system) = % of employee records with no open issue raised in that system
A report is "certifiable" only when no CRITICAL issue touches it, whatever its percentage.
"""

from typing import Dict, List, Any, Set
from collections import defaultdict
from src.models.issue import QualityIssue, GoldenEmployeeRecord, Severity

SYSTEMS = ["core_hr", "payroll", "learning", "access_directory"]

def _issue_fields(issue: QualityIssue) -> Set[str]:
    """Bare field names an issue touches (its conflicting fields and the field the fix changes)."""
    return set(issue.fields_in_conflict) | {issue.recommended_target_field}

class TrustScoreCalculator:
    def __init__(self, report_dependencies: Dict[str, Dict[str, Any]]):
        self.report_dependencies = report_dependencies

    def compute_all_trust_scores(self, golden_records: Dict[str, GoldenEmployeeRecord],
                                 issues: List[QualityIssue]) -> Dict[str, Any]:
        population = max(len(golden_records), 1)

        # Entities with open issues, per bare field and per system
        open_issues = [i for i in issues if i.approval_status.value in ("PENDING", "MODIFIED", "APPROVED")]
        by_field: Dict[str, Set[str]] = defaultdict(set)
        by_system: Dict[str, Set[str]] = defaultdict(set)
        for i in open_issues:
            for f in _issue_fields(i):
                by_field[f].add(i.primary_entity_id)
            for s in i.source_systems:
                by_system[s].add(i.primary_entity_id)

        def pct(affected: int) -> float:
            return round(100.0 * (1 - affected / population), 1)

        field_trust_scores = {f: pct(len(ents)) for f, ents in sorted(by_field.items())}
        system_trust_scores = {s: pct(len(by_system.get(s, set()))) for s in SYSTEMS}

        report_trust_scores: Dict[str, Dict[str, Any]] = {}
        for rep_id, meta in self.report_dependencies.items():
            fields = {f.split(".", 1)[-1] for f in meta.get("fields", [])}
            rep_issues = [i for i in open_issues if rep_id in i.affected_reports or (_issue_fields(i) & fields)]
            affected = {i.primary_entity_id for i in rep_issues}
            critical = [i for i in rep_issues if i.severity == Severity.CRITICAL]
            score = pct(len(affected))
            status = "AT RISK" if critical else "HEALTHY" if score >= 99.0 else "WATCH"
            by_cat = defaultdict(int)
            for i in rep_issues:
                by_cat[i.title] += 1
            report_trust_scores[rep_id] = {
                "name": meta.get("name", rep_id),
                "owner": meta.get("owner", "HR Operations"),
                "trust_score": score,
                "status": status,
                "certifiable": not critical,
                "records_affected": len(affected),
                "critical_issues": len(critical),
                "blocking_issues_count": len(rep_issues),
                "field_scores": {f: field_trust_scores.get(f, 100.0) for f in sorted(fields)},
                "primary_risks": [f"{t} ({n})" for t, n in sorted(by_cat.items(), key=lambda kv: -kv[1])[:3]],
            }

        scores = [r["trust_score"] for r in report_trust_scores.values()]
        global_score = round(sum(scores) / max(len(scores), 1), 1)
        return {
            "global_trust_score": global_score,
            "system_trust_scores": system_trust_scores,
            "field_trust_scores": field_trust_scores,
            "report_trust_scores": report_trust_scores,
            "method": "Share of employee records with no open issue on the fields each report uses; "
                      "a report is not certifiable while any CRITICAL issue touches it.",
        }
