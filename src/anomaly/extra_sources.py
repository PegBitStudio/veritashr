"""
Generic onboarding for any additional HR system extract (the "51st system").

Any table in the data folder that is not one of the four core systems is treated as an extra
source: its columns are mapped onto Core HR's canonical fields, its employee reference column
is found by value overlap with Core HR IDs, each row is linked with the same two-pass matcher,
and every field it shares with Core HR is compared. No code or configuration is needed;
a mapping can still be pinned in schema_mapping.json under the file's system name.
"""

import os
from typing import Dict, List, Any, Optional

from src.models.issue import QualityIssue, IssueCategory, Severity, EvidenceItem
from src.ingestion.schema_mapper import CANONICAL_SCHEMAS, DATE_FIELDS, STATUS_MAPS, norm_header, parse_any_date
from src.matching.record_linker import normalize_name, jaro_winkler_similarity

LEAVER = {"TERMINATED", "RESIGNED"}
COMPARED = [  # field, category, impact, severity
    ("department_code", IssueCategory.DEPARTMENT_CONFLICT, 55.0, Severity.MEDIUM),
    ("job_title", IssueCategory.JOB_CONFLICT, 50.0, Severity.MEDIUM),
    ("job_grade", IssueCategory.FIELD_CONFLICT, 50.0, Severity.MEDIUM),
    ("work_location", IssueCategory.FIELD_CONFLICT, 40.0, Severity.LOW),
    ("hire_date", IssueCategory.DATE_MISMATCH, 50.0, Severity.MEDIUM),
    ("date_of_birth", IssueCategory.DATE_MISMATCH, 45.0, Severity.MEDIUM),
]

def register_extra_schema(system: str):
    """Extra sources use Core HR's canonical fields, with the Core HR ID treated as a reference."""
    core = CANONICAL_SCHEMAS["core_hr"]
    schema = {"employee_ref": core["employee_id"] + ["employee_ref", "emp_ref", "hr_id", "core_id"]}
    schema.update({k: v for k, v in core.items() if k != "employee_id"})
    CANONICAL_SCHEMAS[system] = schema
    DATE_FIELDS[system] = ["date_of_birth", "hire_date", "termination_date"]

def system_name(filename: str) -> str:
    return norm_header(os.path.splitext(os.path.basename(filename))[0])[:40] or "extra"

def check_extra_source(system: str, rows: List[Dict[str, Any]], resolver, golden, catalog) -> List[QualityIssue]:
    issues: List[QualityIssue] = []

    def keys(r):
        return r.get("employee_ref"), r.get("full_name") or f"{r.get('first_name', '')} {r.get('last_name', '')}".strip(), {
            "department_code": (r.get("department_code") or "").upper(), "hire_date": r.get("hire_date_iso")}

    for r, g in resolver._link_all(rows, system, keys):
        ev_head = [EvidenceItem(system, "employee_ref", r.get("employee_ref")),
                   EvidenceItem(system, "link_method", g.link_methods.get(system))]

        # Leaver still active (or active employee marked as leaver) in the extra system
        st = r.get("employment_status")
        if st and g.employment_status:
            if g.employment_status in LEAVER and st == "ACTIVE":
                issues.append(_issue(system, g, IssueCategory.STATUS_CONFLICT, Severity.HIGH, "employment_status",
                    f"{g.canonical_id} left ({g.employment_status} in Core HR, {g.termination_date or 'no date'}) but is still ACTIVE in {system}.",
                    st, g.employment_status, 85.0, ev_head, "Leavers must be closed in every downstream system."))
            elif g.employment_status == "ACTIVE" and st in LEAVER:
                issues.append(_issue(system, g, IssueCategory.STATUS_CONFLICT, Severity.MEDIUM, "employment_status",
                    f"{g.canonical_id} is ACTIVE in Core HR but {st} in {system}.", st, g.employment_status, 60.0, ev_head,
                    "Core HR is the system of record for employment status."))

        for field, cat, impact, sev in COMPARED:
            mine, truth = (r.get(field) or "").strip(), (getattr(g, field) or "").strip()
            if not mine or not truth:
                continue
            if field.endswith("date") or field == "date_of_birth":
                a, b = parse_any_date(r.get(field + "_iso") or mine), parse_any_date(truth)
                differs = a and b and abs((a - b).days) > 1
            elif field == "job_title":
                differs = jaro_winkler_similarity(normalize_name(mine), normalize_name(truth)) < 0.93
            else:
                differs = mine.upper() != truth.upper()
            if differs:
                issues.append(_issue(system, g, cat, sev, field,
                    f"{g.canonical_id}: {system} holds {field} '{mine}' but Core HR holds '{truth}'.",
                    mine, truth, impact, ev_head, "Core HR is the system of record; downstream copies should match it."))

        # Same ID, different person
        nm = normalize_name(r.get("full_name") or f"{r.get('first_name', '')} {r.get('last_name', '')}")
        if "id" in g.link_methods.get(system, "") and nm and g.full_name and \
                sorted(nm.split()) != sorted(normalize_name(g.full_name).split()) and \
                jaro_winkler_similarity(nm, normalize_name(g.full_name)) < 0.85:
            issues.append(_issue(system, g, IssueCategory.NAME_CONFLICT, Severity.MEDIUM, "full_name",
                f"{g.canonical_id} is '{g.full_name}' in Core HR but '{r.get('full_name') or nm}' in {system}.",
                r.get("full_name") or nm, g.full_name, 50.0, ev_head, "Same ID with a different name may be a mis-link; confirm identity."))

    for r in resolver.unlinked.get(system, []):
        if r.get("employment_status") in (None, "", "ACTIVE"):
            ref = r.get("employee_ref") or "(none)"
            issues.append(QualityIssue(
                issue_id=f"ERR-ORPHAN-{system.upper()}-{norm_header(ref) or len(issues)}", category=IssueCategory.GHOST_RECORD,
                severity=Severity.HIGH, title=f"Record in {system} With No Core HR Employee",
                description=f"{system} has a record (ref '{ref}', {r.get('full_name') or 'no name'}) that matches no Core HR employee by ID or name.",
                primary_entity_id=r.get("employee_ref") or ref, entity_name=r.get("full_name") or "Unknown",
                source_systems=[system, "core_hr"], fields_in_conflict=["employee_ref"],
                evidence_trail=[EvidenceItem(system, "employee_ref", ref), EvidenceItem("core_hr", "match_search", "No ID or name match", is_authoritative=True)],
                suggested_fix=f"Verify the person with HR; close the {system} record if they are not an employee.",
                recommended_target_system=system, recommended_target_field="employment_status", recommended_target_value="[VERIFY_WITH_HR]",
                confidence_score=0.8, rationale="Every record in a downstream HR system must belong to a Core HR employee.",
                impact_score=70.0, affected_reports=[]))
    return issues

def _issue(system, g, cat, sev, field, text, current, suggested, impact, ev_head, why) -> QualityIssue:
    return QualityIssue(
        issue_id=f"ERR-{system.upper()}-{field.upper()}-{g.canonical_id}", category=cat, severity=sev,
        title=f"{field.replace('_', ' ').title()} Differs Between Core HR and {system}",
        description=text, primary_entity_id=g.canonical_id, entity_name=g.full_name or "Unknown",
        source_systems=["core_hr", system], fields_in_conflict=[field],
        evidence_trail=[EvidenceItem("core_hr", field, suggested, is_authoritative=True), EvidenceItem(system, field, current)] + ev_head,
        suggested_fix=f"Update {system}.{field} to '{suggested}'.", recommended_target_system=system,
        recommended_target_field=field, recommended_target_value=suggested, confidence_score=0.9, rationale=why,
        impact_score=impact, affected_reports=[])
