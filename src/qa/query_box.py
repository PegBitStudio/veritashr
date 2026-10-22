"""
"Ask HR Truth" plain-language question box for VeritasHR.

Turns a question into an explicit, inspectable query (metric + filters) over the reconciled
golden records, then answers with:
  - the number, and a breakdown
  - how the question was interpreted (so a wrong reading is visible, never silent)
  - which source system each field came from
  - a caveat counting open data-quality issues that touch the records and fields used
Runs locally with deterministic rules; no question or data leaves the machine.
If a question cannot be mapped to known fields, it says so instead of guessing.
"""

import re
from collections import Counter
from typing import Dict, List, Any, Optional, Callable, Tuple
from src.models.issue import GoldenEmployeeRecord, QualityIssue, IssueCategory

FIELD_SOURCE = {
    "employment_status": "core_hr", "work_location": "core_hr", "department_code": "core_hr",
    "job_grade": "core_hr", "nationality": "core_hr", "job_title": "core_hr", "gender": "core_hr",
    "monthly_basic_aed": "payroll", "pay_status": "payroll",
    "training_compliance_status": "learning", "aviation_safety_cert": "learning",
    "ad_account_status": "access_directory",
}
SOURCE_FILE = {"core_hr": "Core HR (system of record)", "payroll": "Payroll", "learning": "Learning (LMS)",
               "access_directory": "Access Directory"}

STATUS_WORDS = [("on leave", "ON_LEAVE"), ("terminated", "TERMINATED"), ("leaver", "TERMINATED"), ("resigned", "RESIGNED"),
                ("suspended", "SUSPENDED"), ("active", "ACTIVE"), ("current", "ACTIVE")]
CITY_ALIASES = {"dubai": ["DXB", "DWC", "DUBAI"], "abu dhabi": ["AUH", "ABU DHABI"], "london": ["LHR", "LONDON"],
                "new york": ["JFK", "NEW YORK"], "singapore": ["SIN", "SINGAPORE"]}
DEPT_ALIASES = {"pilot": "EK-FLIGHT-OPS", "flight crew": "EK-FLIGHT-OPS", "flight ops": "EK-FLIGHT-OPS",
                "cabin crew": "EK-CABIN-CREW", "engineer": "EK-ENG", "cargo": "DNATA-CARGO", "ground": "DNATA-GROUND-SVCS",
                "travel": "DNATA-TRAVEL", "airport": "EK-AIRPORT-SVCS", " it ": "EK-IT", "hr ": "EK-HR", "commercial": "EK-COMMERCIAL"}
NATIONALITY_WORDS = {"emirati": "AE", "uae national": "AE", "indian": "IN", "pakistani": "PK", "filipino": "PH",
                     "british": "GB", "egyptian": "EG", "jordanian": "JO", "lebanese": "LB"}

class AskHRTruthEngine:
    def __init__(self, golden_records: Dict[str, GoldenEmployeeRecord], issues: List[QualityIssue], catalog=None):
        self.records = list(golden_records.values())
        self.issues = issues
        self.catalog = catalog
        self.issues_by_entity: Dict[str, List[QualityIssue]] = {}
        for i in issues:
            self.issues_by_entity.setdefault(i.primary_entity_id, []).append(i)
        self.locations = sorted(getattr(catalog, "locations", set()) or {r.work_location for r in self.records if r.work_location})
        self.departments = sorted(getattr(catalog, "departments", set()) or {r.department_code for r in self.records if r.department_code})
        self.descriptions = getattr(catalog, "code_descriptions", {}) or {}

    # ------------------------------------------------------------------
    def _parse(self, q: str) -> Tuple[str, List[Tuple[str, str, Callable]], List[str]]:
        """Returns (metric, filters[(field, label, predicate)], notes)."""
        ql = f" {q.lower()} "
        filters: List[Tuple[str, str, Callable]] = []
        notes: List[str] = []

        if re.search(r"\b(average|avg|mean)\b", ql) and re.search(r"salar|pay|wage", ql):
            metric = "avg_salary"
        elif re.search(r"\b(total|sum)\b", ql) and re.search(r"salar|payroll|pay|wage|cost", ql):
            metric = "sum_salary"
        else:
            metric = "count"

        # Special cross-system questions
        if re.search(r"ghost|terminated.*(paid|payroll|salary)|still (paid|on payroll)", ql):
            return "ghost", [], notes
        if re.search(r"(leaver|terminated|ex-?employee).*(access|account|login|logon)|zombie", ql):
            return "zombie", [], notes

        for word, status in STATUS_WORDS:
            if re.search(rf"\b{word}\b", ql):
                filters.append(("employment_status", f"status = {status}", lambda r, s=status: r.employment_status == s))
                break
        else:
            filters.append(("employment_status", "status = ACTIVE (assumed)", lambda r: r.employment_status == "ACTIVE"))
            notes.append("No status given, so only ACTIVE employees are counted.")

        # Location: city names or codes, matched against code descriptions from the data dictionary
        locs = set()
        for city, keys in CITY_ALIASES.items():
            if city in ql:
                locs |= {c for c in self.locations if any(k in c or k in self.descriptions.get(c, "").upper() for k in keys)}
        for c in self.locations:
            if re.search(rf"\b{re.escape(c.lower())}\b", ql) or (len(c.split("-")[-1]) > 2 and f" {c.split('-')[-1].lower()} " in ql):
                locs.add(c)
        if locs:
            filters.append(("work_location", f"location in {sorted(locs)}", lambda r, L=locs: r.work_location in L))

        # Department: aliases, codes, or words from the code description
        depts = set()
        for alias, code in DEPT_ALIASES.items():
            if alias in ql and code in self.departments:
                depts.add(code)
        for c in self.departments:
            if c.lower() in ql:
                depts.add(c)
        if depts:
            filters.append(("department_code", f"department in {sorted(depts)}", lambda r, D=depts: r.department_code in D))

        for m in re.findall(r"\b((?:g|cr|t|e)\d{2})\b", ql):
            filters.append(("job_grade", f"grade = {m.upper()}", lambda r, g=m.upper(): r.job_grade == g))
        for word, code in NATIONALITY_WORDS.items():
            if word in ql:
                filters.append(("nationality", f"nationality = {code}", lambda r, c=code: r.nationality == c))
        if re.search(r"female|women", ql):
            filters.append(("gender", "gender = F", lambda r: (r.gender or "").upper().startswith("F")))
        elif re.search(r"\bmale\b|\bmen\b", ql):
            filters.append(("gender", "gender = M", lambda r: (r.gender or "").upper().startswith("M")))
        if re.search(r"expired|overdue|non.?compliant", ql) and re.search(r"train|cert|complian", ql):
            filters.append(("training_compliance_status", "training compliance = EXPIRED",
                            lambda r: (r.training_compliance_status or "").upper() in ("EXPIRED", "NON_COMPLIANT", "OVERDUE")))
        return metric, filters, notes

    # ------------------------------------------------------------------
    def answer_query(self, query: str) -> Dict[str, Any]:
        metric, filters, notes = self._parse(query or "")
        if metric == "ghost":
            return self._issue_answer(query, IssueCategory.GHOST_RECORD, "terminated or unknown people still being paid",
                                      "Core HR employment_status vs Payroll pay_status")
        if metric == "zombie":
            return self._issue_answer(query, IssueCategory.SECURITY_EXPOSURE, "leavers or unknown people with active directory access",
                                      "Core HR employment_status vs Access Directory account_status")

        understood = [f for f in filters if "(assumed)" not in f[1]]
        if not understood and metric == "count" and not re.search(r"employ|staff|headcount|people|workforce", (query or "").lower()):
            return {
                "question": query, "headline_answer": "Sorry, I could not map this question to HR data fields.",
                "interpretation": "No known status, location, department, grade, nationality or salary terms found.",
                "breakdown": {"Try": ["How many active employees in Dubai?", "Total monthly salary for cabin crew",
                                      "How many Emirati employees in grade G05?", "How many pilots have expired training?"]},
                "authoritative_source": "-", "trust_confidence": "-", "quality_caveat": "No answer was guessed."}

        rows = [r for r in self.records if all(pred(r) for _, _, pred in filters)]
        fields = [f for f, _, _ in filters]
        if metric in ("sum_salary", "avg_salary"):
            fields.append("monthly_basic_aed")
            paid = [r for r in rows if r.monthly_basic_aed]
            total = sum(r.monthly_basic_aed for r in paid)
            if metric == "sum_salary":
                headline = f"AED {total:,.0f} total monthly basic salary ({len(paid):,} employees)"
            else:
                headline = f"AED {total / max(len(paid), 1):,.0f} average monthly basic salary ({len(paid):,} employees)"
            if len(paid) < len(rows):
                notes.append(f"{len(rows) - len(paid)} matching employees have no payroll salary and are excluded.")
        else:
            headline = f"{len(rows):,} employees"

        group_field = "work_location" if "work_location" in fields or not any(f == "department_code" for f in fields) else "department_code"
        breakdown = dict(Counter(getattr(r, group_field) or "(blank)" for r in rows).most_common(10))

        # Caveat: open issues on these records that touch the fields this answer relies on
        field_names = set(fields) | {"employment_status"}
        aliases = {"monthly_basic_aed": {"monthly_basic_aed", "pay_status"}, "employment_status": {"employment_status", "pay_status", "termination_date"},
                   "work_location": {"work_location"}, "department_code": {"department_code", "cost_center", "assigned_department"}}
        touched = set().union(*(aliases.get(f, {f}) for f in field_names))
        ids = {r.canonical_id for r in rows}
        affecting = [i for e in ids for i in self.issues_by_entity.get(e, []) if touched & set(i.fields_in_conflict)]
        affected_ids = {i.primary_entity_id for i in affecting}
        share = len(affected_ids) / max(len(ids), 1)
        trust = round(100 * (1 - share), 1)
        if affecting:
            cats = Counter(i.category.value for i in affecting).most_common(3)
            caveat = (f"{len(affected_ids)} of {len(ids):,} records behind this number have open issues on the fields used "
                      f"({', '.join(f'{c}: {n}' for c, n in cats)}). The figure could move by up to {len(affected_ids)} once fixed.")
        else:
            caveat = "No open data-quality issues touch the records or fields behind this number."
        # Records excluded only because a code is invalid, whose most likely correct value matches the filter
        missed = set()
        for f, label, pred in filters:
            for i in self.issues:
                if i.recommended_target_field == f and i.category == IssueCategory.INVALID_CODE and i.primary_entity_id not in ids:
                    probe = next((r for r in self.records if r.canonical_id == i.primary_entity_id), None)
                    if probe is None:
                        continue
                    original = getattr(probe, f)
                    setattr(probe, f, i.recommended_target_value)
                    try:
                        if all(p_(probe) for _, _, p_ in filters):
                            missed.add(i.primary_entity_id)
                    finally:
                        setattr(probe, f, original)
        if missed:
            caveat += f" However, {len(missed)} more employee(s) are left out because their code is invalid and its most likely correct value matches this question (the true figure is probably {len(ids) + len(missed):,})."
            trust = round(100 * len(ids) / (len(ids) + len(missed) + len(affected_ids)), 1) if ids else trust
        if notes:
            caveat = " ".join(notes) + " " + caveat

        sources = sorted({FIELD_SOURCE.get(f, "core_hr") for f in fields} or {"core_hr"})
        return {
            "question": query,
            "headline_answer": headline,
            "interpretation": f"{metric.replace('_', ' ')} of golden records where " + (" AND ".join(l for _, l, _ in filters) or "(no filter)"),
            "breakdown": {f"by {group_field}": breakdown},
            "authoritative_source": " + ".join(f"{SOURCE_FILE[s]} [{', '.join(sorted(f for f in fields if FIELD_SOURCE.get(f, 'core_hr') == s)) or 'records'}]" for s in sources),
            "trust_confidence": f"{trust}%",
            "quality_caveat": caveat,
        }

    def _issue_answer(self, query, category, what, source):
        found = [i for i in self.issues if i.category == category]
        monthly = sum(i.financial_risk_aed for i in found) / 12
        breakdown = {"Records": len(found)}
        if monthly:
            breakdown.update({"Monthly exposure (AED)": f"{monthly:,.0f}", "Annualised exposure (AED)": f"{monthly * 12:,.0f}"})
        breakdown["Top cases"] = [f"{i.primary_entity_id}: {i.entity_name}" for i in found[:5]]
        return {
            "question": query, "headline_answer": f"{len(found)} {what}",
            "interpretation": f"open {category.value} issues from cross-system reconciliation",
            "breakdown": breakdown, "authoritative_source": source,
            "trust_confidence": f"{100 * sum(i.confidence_score for i in found) / max(len(found), 1):.0f}% average detection confidence",
            "quality_caveat": "These are detected issues awaiting steward review; none has been changed in any system."}
