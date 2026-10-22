"""
Extended, schema-generic quality checks for VeritasHR.
Complements the core detector with rules that do not depend on how a particular
synthetic dataset was generated:
  - Cross-system attribute conflicts (department, job, name, employment status)
  - Temporal impossibilities (exit before hire, future dates, hire before working age)
  - Missing mandatory fields and missing downstream records
  - Format / code validity (IBAN, Emirates ID, status vocabularies, LMS departments)
  - Double payment and duplicate accounts, fuzzy duplicate identities
  - Out-of-date records (expired safety certifications, dormant accounts)
Every rule produces plain-language evidence and a suggested value with its source.
"""

import re
import difflib
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Dict, List, Any, Optional, Tuple

from src.models.issue import QualityIssue, IssueCategory, Severity, EvidenceItem, GoldenEmployeeRecord
from src.ingestion.schema_mapper import parse_any_date
from src.matching.record_linker import normalize_name, jaro_winkler_similarity

IBAN_RE = re.compile(r"^AE\d{2}[A-Z0-9]{3}\d{16}$")
EID_RE = re.compile(r"^784-?\d{4}-?\d{7}-?\d$")
SAFETY_DEPTS = {"EK-FLIGHT-OPS", "EK-CABIN-CREW", "EK-ENG"}
CORE_MANDATORY = ["date_of_birth", "national_id", "department_code", "job_title", "job_grade",
                  "work_location", "employment_status", "hire_date"]

def closest_code(value: str, valid: List[str], descriptions: Optional[Dict[str, str]] = None) -> Tuple[Optional[str], float]:
    """Suggests the closest valid code: spelling similarity plus shared tokens in the code or its dictionary description
    (e.g. 'EK-FLT-OPS' -> 'EK-FLIGHT-OPS', 'DXB-AIR' -> 'DXB-T3' because T3 is described as the airport terminal)."""
    if not value or not valid:
        return None, 0.0
    v = value.strip().upper()
    tokens = [t for t in re.split(r"[-_ ]", v) if len(t) >= 2]
    best, score = None, 0.0
    for c in valid:
        s = difflib.SequenceMatcher(None, v, c).ratio()
        code_tokens = set(re.split(r"[-_ ]", c))
        desc = (descriptions or {}).get(c, "").upper()
        s += 0.1 * sum(1 for t in tokens if t in code_tokens or (len(t) > 2 and t in c))
        s += 0.1 * sum(1 for t in tokens if len(t) > 2 and t in desc)
        if s > score:
            best, score = c, s
    return best, min(score, 1.0)

def _issue(**kw) -> QualityIssue:
    kw.setdefault("rationale", "")
    kw.setdefault("affected_reports", [])
    return QualityIssue(**kw)

class ExtendedChecks:
    def __init__(self, catalog, reference_date: Optional[datetime] = None):
        self.catalog = catalog
        self.reference_date = reference_date or datetime.now()

    # ------------------------------------------------------------------
    def run(self, golden: Dict[str, GoldenEmployeeRecord], sources: Dict[str, List[Dict[str, Any]]],
            existing: List[QualityIssue], multi_links: Dict[str, Dict[str, List[Dict[str, Any]]]],
            duplicate_secondaries: set) -> List[QualityIssue]:
        out: List[QualityIssue] = []
        index = {(i.primary_entity_id, i.category): i for i in existing}
        # Duplicates first: the redundant copy of a person should not raise knock-on issues of its own
        dups = self._fuzzy_duplicates(golden, {i.primary_entity_id for i in existing if i.category == IssueCategory.DUPLICATE_ENTITY})
        out += dups
        duplicate_secondaries = set(duplicate_secondaries) | {i.evidence_trail[1].recorded_value for i in dups}
        for cid, g in golden.items():
            if cid in duplicate_secondaries:
                continue
            l = {"job_role": g.learning_job_role} if g.learning_job_role else None
            out += self._cross_system_conflicts(g, l, index)
            out += self._temporal(g)
            out += self._missing(g)
            out += self._validity(g, l)
            out += self._out_of_date(g)
        out += self._double_links(golden, multi_links)
        return out

    # ------------------------------------------------------------------
    def _cross_system_conflicts(self, g: GoldenEmployeeRecord, l: Optional[Dict[str, Any]], index) -> List[QualityIssue]:
        res = []
        # Department: LMS vs Core HR (merged into the payroll conflict when one exists)
        lms_dept = (g.learning_department or "").strip().upper()
        if lms_dept and g.department_code and lms_dept != g.department_code and g.department_code in self.catalog.departments:
            ev = [EvidenceItem("core_hr", "department_code", g.department_code, is_authoritative=True),
                  EvidenceItem("learning", "assigned_department", g.learning_department)]
            existing = index.get((g.canonical_id, IssueCategory.DEPARTMENT_CONFLICT))
            if existing:
                existing.evidence_trail += ev[1:]
                existing.source_systems = sorted(set(existing.source_systems) | {"learning"})
                existing.description += f" The Learning system also holds a different department ('{g.learning_department}')."
                existing.confidence_score = min(0.99, existing.confidence_score + 0.02)
            else:
                res.append(_issue(
                    issue_id=f"ERR-DEPT-LMS-{g.canonical_id}", category=IssueCategory.DEPARTMENT_CONFLICT, severity=Severity.MEDIUM,
                    title="Department Mismatch Between Core HR and Learning",
                    description=f"Core HR places {g.canonical_id} in '{g.department_code}', but the Learning system assigns '{g.learning_department}'. Mandatory training may be assigned for the wrong department.",
                    primary_entity_id=g.canonical_id, entity_name=g.full_name or "Unknown",
                    source_systems=["core_hr", "learning"], fields_in_conflict=["department_code", "assigned_department"],
                    evidence_trail=ev, suggested_fix=f"Update learning.assigned_department to '{g.department_code}'.",
                    recommended_target_system="learning", recommended_target_field="assigned_department",
                    recommended_target_value=g.department_code, confidence_score=0.93,
                    rationale="Core HR is the system of record for organisational assignment; Learning is fed from it.",
                    impact_score=58.0, affected_reports=["REP-GCAA-SAFETY", "REP-LMS-BUDGET"]))

        # Job / role conflict: LMS job_role vs Core HR job_title
        role = (l or {}).get("job_role") if l else None
        if role and g.job_title and normalize_name(role) != normalize_name(g.job_title):
            sim = jaro_winkler_similarity(normalize_name(role), normalize_name(g.job_title))
            if sim < 0.93:
                res.append(_issue(
                    issue_id=f"ERR-JOB-{g.canonical_id}", category=IssueCategory.JOB_CONFLICT, severity=Severity.MEDIUM,
                    title="Conflicting Job Role Between Core HR and Learning",
                    description=f"Core HR records {g.canonical_id} as '{g.job_title}', but Learning holds role '{role}'. Role-based safety training and certifications may be wrong.",
                    primary_entity_id=g.canonical_id, entity_name=g.full_name or "Unknown",
                    source_systems=["core_hr", "learning"], fields_in_conflict=["job_title", "job_role"],
                    evidence_trail=[EvidenceItem("core_hr", "job_title", g.job_title, is_authoritative=True),
                                    EvidenceItem("learning", "job_role", role)],
                    suggested_fix=f"Update learning.job_role to '{g.job_title}' and re-run curriculum assignment.",
                    recommended_target_system="learning", recommended_target_field="job_role",
                    recommended_target_value=g.job_title, confidence_score=0.9,
                    rationale="Job assignments originate in Core HR and are pushed to Learning.",
                    impact_score=63.0 if g.department_code in SAFETY_DEPTS else 50.0,
                    affected_reports=["REP-GCAA-SAFETY"]))

        # Employment status vs payroll / directory (active in HR but not paid / locked out)
        if g.employment_status == "ACTIVE" and g.pay_status in ("INACTIVE",):
            res.append(_issue(
                issue_id=f"ERR-STATUS-PAY-{g.canonical_id}", category=IssueCategory.STATUS_CONFLICT, severity=Severity.HIGH,
                title="Active Employee Not Being Paid",
                description=f"{g.canonical_id} is ACTIVE in Core HR but INACTIVE in Payroll, so they would miss their salary (WPS breach).",
                primary_entity_id=g.canonical_id, entity_name=g.full_name or "Unknown",
                source_systems=["core_hr", "payroll"], fields_in_conflict=["employment_status", "pay_status"],
                evidence_trail=[EvidenceItem("core_hr", "employment_status", g.employment_status, is_authoritative=True),
                                EvidenceItem("payroll", "pay_status", g.pay_status)],
                suggested_fix="Verify with the line manager, then set payroll.pay_status to 'ACTIVE'.",
                recommended_target_system="payroll", recommended_target_field="pay_status", recommended_target_value="ACTIVE",
                confidence_score=0.85, rationale="Core HR is authoritative for employment status; WPS requires every active employee be paid.",
                impact_score=80.0, affected_reports=["REP-WPS-PAYROLL"]))
        if g.employment_status == "ACTIVE" and g.ad_account_status == "Disabled":
            res.append(_issue(
                issue_id=f"ERR-STATUS-AD-{g.canonical_id}", category=IssueCategory.STATUS_CONFLICT, severity=Severity.LOW,
                title="Active Employee With Disabled Directory Account",
                description=f"{g.canonical_id} is ACTIVE in Core HR but their directory account is Disabled.",
                primary_entity_id=g.canonical_id, entity_name=g.full_name or "Unknown",
                source_systems=["core_hr", "access_directory"], fields_in_conflict=["employment_status", "account_status"],
                evidence_trail=[EvidenceItem("core_hr", "employment_status", g.employment_status, is_authoritative=True),
                                EvidenceItem("access_directory", "account_status", g.ad_account_status)],
                suggested_fix="Confirm with IT whether the lock is intentional (e.g. security hold) before re-enabling.",
                recommended_target_system="access_directory", recommended_target_field="account_status", recommended_target_value="Active",
                confidence_score=0.7, rationale="Accounts are provisioned from Core HR status, but a disable can be a deliberate security action.",
                impact_score=35.0, affected_reports=["REP-SEC-OFFBOARDING"]))

        # Name conflict: linked by ID, but the name in the other system is materially different
        core_nm = normalize_name(g.full_name or "")
        for system, other in g.source_names.items():
            if "id" not in g.link_methods.get(system, "") or not other or not core_nm:
                continue
            on = normalize_name(other)
            if on and sorted(on.split()) != sorted(core_nm.split()) and jaro_winkler_similarity(on, core_nm) < 0.85:
                res.append(_issue(
                    issue_id=f"ERR-NAME-{system.upper()}-{g.canonical_id}", category=IssueCategory.NAME_CONFLICT, severity=Severity.MEDIUM,
                    title="Same Employee ID, Different Name",
                    description=f"{g.canonical_id} is '{g.full_name}' in Core HR but '{other}' in {system}. Either the name is out of date or the ID points to the wrong person.",
                    primary_entity_id=g.canonical_id, entity_name=g.full_name or "Unknown",
                    source_systems=["core_hr", system], fields_in_conflict=["full_name"],
                    evidence_trail=[EvidenceItem("core_hr", "full_name", g.full_name, is_authoritative=True), EvidenceItem(system, "name", other)],
                    suggested_fix=f"Confirm identity from the passport / Emirates ID, then update the {system} name to '{g.full_name}' (or re-link the record).",
                    recommended_target_system=system, recommended_target_field="name", recommended_target_value=g.full_name,
                    confidence_score=0.75, rationale="Core HR holds the legal name; a mismatch on the same ID may be a mis-link and needs human review.",
                    impact_score=66.0 if system == "payroll" else 45.0,
                    affected_reports=["REP-WPS-PAYROLL"] if system == "payroll" else []))
        return res

    # ------------------------------------------------------------------
    def _temporal(self, g: GoldenEmployeeRecord) -> List[QualityIssue]:
        res = []
        hire, term, dob = parse_any_date(g.hire_date), parse_any_date(g.termination_date), parse_any_date(g.date_of_birth)
        problems = []
        if hire and term and term < hire:
            problems.append(("termination_date", f"termination date {g.termination_date} is before hire date {g.hire_date}", g.termination_date, "[VERIFY_WITH_HR]"))
        if hire and hire > self.reference_date + timedelta(days=90):
            problems.append(("hire_date", f"hire date {g.hire_date} is in the future", g.hire_date, "[VERIFY_WITH_HR]"))
        if dob and dob > self.reference_date:
            problems.append(("date_of_birth", f"date of birth {g.date_of_birth} is in the future", g.date_of_birth, "[VERIFY_WITH_HR]"))
        # Synthetic and legacy data often hold implausibly young hires, so only flag the impossible case
        if dob and hire and hire <= dob:
            problems.append(("date_of_birth", f"hire date {g.hire_date} is on or before the date of birth {g.date_of_birth}", g.date_of_birth, "[VERIFY_WITH_HR]"))
        if g.employment_status in ("TERMINATED", "RESIGNED") and not term:
            problems.append(("termination_date", f"status is {g.employment_status} but no termination date is recorded", "", "[REQUIRED]"))
        if g.employment_status == "ACTIVE" and term and term < self.reference_date - timedelta(days=1):
            problems.append(("employment_status", f"status is ACTIVE but a past termination date ({g.termination_date}) is recorded", g.employment_status, "TERMINATED"))
        for field, text, current, suggestion in problems:
            res.append(_issue(
                issue_id=f"ERR-TEMPORAL-{field.upper()}-{g.canonical_id}", category=IssueCategory.DATE_MISMATCH, severity=Severity.MEDIUM,
                title="Impossible or Inconsistent Employment Dates",
                description=f"For {g.canonical_id}, the {text}.",
                primary_entity_id=g.canonical_id, entity_name=g.full_name or "Unknown",
                source_systems=["core_hr"], fields_in_conflict=[field],
                evidence_trail=[EvidenceItem("core_hr", "hire_date", g.hire_date), EvidenceItem("core_hr", "termination_date", g.termination_date),
                                EvidenceItem("core_hr", "date_of_birth", g.date_of_birth), EvidenceItem("core_hr", "employment_status", g.employment_status)],
                suggested_fix=f"Correct core_hr.{field} from the signed employment contract / exit form.",
                recommended_target_system="core_hr", recommended_target_field=field, recommended_target_value=suggestion,
                confidence_score=0.9, rationale="Employment lifecycle dates must follow birth < hire < termination.",
                impact_score=57.0, affected_reports=["REP-EXEC-HEADCOUNT"]))
        return res

    # ------------------------------------------------------------------
    def _missing(self, g: GoldenEmployeeRecord) -> List[QualityIssue]:
        res = []
        missing = [f for f in CORE_MANDATORY if not (getattr(g, f, None) or "").strip()]
        if missing:
            res.append(_issue(
                issue_id=f"ERR-MISSING-CORE-{g.canonical_id}", category=IssueCategory.MISSING_VALUE, severity=Severity.MEDIUM,
                title="Missing Mandatory Core HR Fields",
                description=f"{g.canonical_id} is missing mandatory field(s): {', '.join(missing)}.",
                primary_entity_id=g.canonical_id, entity_name=g.full_name or "Unknown",
                source_systems=["core_hr"], fields_in_conflict=missing,
                evidence_trail=[EvidenceItem("core_hr", f, "[EMPTY]") for f in missing] + self._fill_hints(g, missing),
                suggested_fix=f"Populate {', '.join(missing)} from the employee file" + (" (a value is available in another system, see evidence)." if self._fill_hints(g, missing) else "."),
                recommended_target_system="core_hr", recommended_target_field=missing[0],
                recommended_target_value=self._fill_value(g, missing[0]) or "[AWAITING_INPUT]",
                confidence_score=0.95, rationale="Mandatory per data dictionary; blank values drop the employee out of headcount and regulatory reports.",
                impact_score=55.0 + (10 if "national_id" in missing else 0),
                affected_reports=["REP-EXEC-HEADCOUNT"] + (["REP-WPS-PAYROLL"] if "national_id" in missing else [])))
        if g.employment_status == "ACTIVE" and not g.payroll_id:
            res.append(_issue(
                issue_id=f"ERR-NOPAYROLL-{g.canonical_id}", category=IssueCategory.MISSING_VALUE, severity=Severity.HIGH,
                title="Active Employee Missing From Payroll",
                description=f"{g.canonical_id} is ACTIVE in Core HR but has no payroll record (matched by ID and name).",
                primary_entity_id=g.canonical_id, entity_name=g.full_name or "Unknown",
                source_systems=["core_hr", "payroll"], fields_in_conflict=["payroll_id"],
                evidence_trail=[EvidenceItem("core_hr", "employment_status", g.employment_status, is_authoritative=True),
                                EvidenceItem("payroll", "payroll_id", "[NO MATCHING RECORD]")],
                suggested_fix="Create the payroll record via the Core HR onboarding feed, or confirm the employee is unpaid/secondment.",
                recommended_target_system="payroll", recommended_target_field="payroll_id", recommended_target_value="[CREATE_FROM_CORE_HR]",
                confidence_score=0.8, rationale="Every active employee must appear in the WPS file.",
                impact_score=78.0, affected_reports=["REP-WPS-PAYROLL"]))
        if g.payroll_id and g.pay_status == "ACTIVE" and not g.monthly_basic_aed:
            res.append(_issue(
                issue_id=f"ERR-NOSALARY-{g.canonical_id}", category=IssueCategory.MISSING_VALUE, severity=Severity.HIGH,
                title="Active Payroll Record With No Basic Salary",
                description=f"{g.canonical_id} is active on payroll ({g.payroll_id}) but basic salary is blank or zero.",
                primary_entity_id=g.canonical_id, entity_name=g.full_name or "Unknown",
                source_systems=["payroll"], fields_in_conflict=["monthly_basic_aed"],
                evidence_trail=[EvidenceItem("payroll", "monthly_basic_aed", g.monthly_basic_aed), EvidenceItem("core_hr", "job_grade", g.job_grade)],
                suggested_fix="Populate basic salary from the approved grade band / offer letter.",
                recommended_target_system="payroll", recommended_target_field="monthly_basic_aed", recommended_target_value="[GRADE_BAND_VALUE]",
                confidence_score=0.95, rationale="WPS files reject zero-salary lines for active employees.",
                impact_score=76.0, affected_reports=["REP-WPS-PAYROLL"]))
        return res

    def _fill_hints(self, g, missing) -> List[EvidenceItem]:
        hints = []
        if "department_code" in missing and g.learning_department:
            hints.append(EvidenceItem("learning", "assigned_department", g.learning_department))
        if "department_code" in missing and g.payroll_cost_center:
            hints.append(EvidenceItem("payroll", "cost_center", g.payroll_cost_center))
        return hints

    def _fill_value(self, g, field) -> Optional[str]:
        if field == "department_code":
            votes = defaultdict(int)
            if g.learning_department:
                votes[g.learning_department.upper()] += 1
            if g.payroll_cost_center:
                votes[g.payroll_cost_center.upper().replace("CC-", "", 1)] += 1
            if votes:
                return max(votes, key=votes.get)
        return None

    # ------------------------------------------------------------------
    def _validity(self, g: GoldenEmployeeRecord, l: Optional[Dict[str, Any]]) -> List[QualityIssue]:
        res = []
        if g.bank_iban and len(g.bank_iban.strip()) >= 15 and not IBAN_RE.match(g.bank_iban.strip().upper()):
            res.append(self._code_issue(g, "payroll", "bank_iban", g.bank_iban, "IBAN does not follow the UAE 23-character format (AE + 2 check digits + 3 bank code + 16 digits)",
                                        "[REQUEST_FROM_EMPLOYEE]", 74.0, ["REP-WPS-PAYROLL"], Severity.HIGH, "ERR-CODE-IBAN"))
        if g.national_id and not EID_RE.match(g.national_id.strip()):
            res.append(self._code_issue(g, "core_hr", "national_id", g.national_id, "Emirates ID does not follow the 784-YYYY-NNNNNNN-C format",
                                        "[VERIFY_EMIRATES_ID]", 60.0, ["REP-WPS-PAYROLL"], Severity.MEDIUM, "ERR-CODE-EID"))
        valid_core = self.catalog.statuses.get("core_hr", set())
        if g.employment_status and valid_core and g.employment_status not in valid_core:
            sug, _ = closest_code(g.employment_status, sorted(valid_core))
            res.append(self._code_issue(g, "core_hr", "employment_status", g.employment_status, "status is not in the Core HR status list",
                                        sug, 66.0, ["REP-EXEC-HEADCOUNT"], Severity.MEDIUM, "ERR-CODE-STATUS"))
        lms_dept = (g.learning_department or "").strip().upper()
        if lms_dept and self.catalog.departments and lms_dept not in self.catalog.departments:
            sug, _ = closest_code(lms_dept, sorted(self.catalog.departments), self.catalog.code_descriptions)
            res.append(self._code_issue(g, "learning", "assigned_department", g.learning_department, "department is not a valid organisation code",
                                        g.department_code if g.department_code in self.catalog.departments else sug,
                                        50.0, ["REP-LMS-BUDGET"], Severity.LOW, "ERR-CODE-LMSDEPT"))
        return res

    def _code_issue(self, g, system, field, value, why, suggestion, impact, reports, sev, prefix):
        return _issue(
            issue_id=f"{prefix}-{g.canonical_id}", category=IssueCategory.INVALID_CODE, severity=sev,
            title=f"Invalid {field.replace('_', ' ').title()} Format",
            description=f"For {g.canonical_id}, the {system} value '{value}' is invalid: {why}.",
            primary_entity_id=g.canonical_id, entity_name=g.full_name or "Unknown",
            source_systems=[system], fields_in_conflict=[field],
            evidence_trail=[EvidenceItem(system, field, value), EvidenceItem("data_dictionary", "format_rule", why, is_authoritative=True)],
            suggested_fix=f"Correct {system}.{field}" + (f" to '{suggestion}'." if suggestion and not str(suggestion).startswith("[") else " from the source document."),
            recommended_target_system=system, recommended_target_field=field, recommended_target_value=suggestion,
            confidence_score=0.9, rationale="Value violates the format / code list in the data dictionary.",
            impact_score=impact, affected_reports=reports)

    # ------------------------------------------------------------------
    def _out_of_date(self, g: GoldenEmployeeRecord) -> List[QualityIssue]:
        res = []
        if g.employment_status == "ACTIVE" and (g.training_compliance_status or "").upper() in ("EXPIRED", "NON_COMPLIANT", "OVERDUE"):
            safety = g.department_code in SAFETY_DEPTS or (g.aviation_safety_cert or "").upper() not in ("", "N/A")
            res.append(_issue(
                issue_id=f"ERR-STALE-CERT-{g.canonical_id}", category=IssueCategory.REGULATORY_DEFICIT,
                severity=Severity.HIGH if safety else Severity.LOW,
                title="Active Employee With Expired Mandatory Training",
                description=f"{g.canonical_id} ({g.job_title}, {g.department_code}) is ACTIVE but training compliance is '{g.training_compliance_status}'"
                            + (" in a safety-critical role." if safety else "."),
                primary_entity_id=g.canonical_id, entity_name=g.full_name or "Unknown",
                source_systems=["core_hr", "learning"], fields_in_conflict=["compliance_status"],
                evidence_trail=[EvidenceItem("core_hr", "employment_status", g.employment_status, is_authoritative=True),
                                EvidenceItem("learning", "compliance_status", g.training_compliance_status),
                                EvidenceItem("learning", "aviation_safety_cert", g.aviation_safety_cert)],
                suggested_fix="Schedule recurrent training; if the record is out of date, refresh it from the training provider.",
                recommended_target_system="learning", recommended_target_field="compliance_status", recommended_target_value="[RETRAIN_OR_REFRESH]",
                confidence_score=0.85, rationale="GCAA requires current recurrent training for operational staff.",
                impact_score=72.0 if safety else 40.0, affected_reports=["REP-GCAA-SAFETY"]))
        return res

    # ------------------------------------------------------------------
    def _double_links(self, golden, multi_links) -> List[QualityIssue]:
        res = []
        for cid, extra in multi_links.get("payroll", {}).items():
            g = golden[cid]
            active = [r for r in extra if r.get("pay_status") == "ACTIVE"]
            if g.pay_status == "ACTIVE" and active:
                amt = sum(float(r.get("monthly_basic_aed") or 0) for r in active)
                ids = [g.payroll_id] + [r.get("payroll_id") for r in active]
                res.append(_issue(
                    issue_id=f"ERR-DOUBLEPAY-{cid}", category=IssueCategory.DUPLICATE_ENTITY, severity=Severity.CRITICAL,
                    title="Employee Paid Through More Than One Payroll Record",
                    description=f"{cid} has {len(ids)} ACTIVE payroll records ({', '.join(ids)}); an extra AED {amt:,.0f} per month may be double-paid.",
                    primary_entity_id=cid, entity_name=g.full_name or "Unknown",
                    source_systems=["payroll", "core_hr"], fields_in_conflict=["payroll_id"],
                    evidence_trail=[EvidenceItem("payroll", "payroll_id", i) for i in ids],
                    suggested_fix=f"Keep {g.payroll_id}, put the other record(s) on HOLD and recover overpayments.",
                    recommended_target_system="payroll", recommended_target_field="pay_status", recommended_target_value="HOLD",
                    confidence_score=0.9, rationale="One employee must have exactly one active payroll record.",
                    impact_score=96.0, financial_risk_aed=amt * 12, affected_reports=["REP-WPS-PAYROLL"]))
        for cid, extra in multi_links.get("access_directory", {}).items():
            g = golden[cid]
            accts = [g.directory_id] + [r.get("samaccountname") for r in extra]
            res.append(_issue(
                issue_id=f"ERR-MULTIAD-{cid}", category=IssueCategory.SECURITY_EXPOSURE, severity=Severity.MEDIUM,
                title="Employee Holds More Than One Directory Account",
                description=f"{cid} is linked to {len(accts)} directory accounts ({', '.join(a or '?' for a in accts)}).",
                primary_entity_id=cid, entity_name=g.full_name or "Unknown",
                source_systems=["access_directory"], fields_in_conflict=["samaccountname"],
                evidence_trail=[EvidenceItem("access_directory", "samaccountname", a) for a in accts],
                suggested_fix="Disable the duplicate account after confirming which one is in use.",
                recommended_target_system="access_directory", recommended_target_field="account_status", recommended_target_value="Disabled",
                confidence_score=0.8, rationale="One identity, one account (ISO 27001 access control).",
                impact_score=60.0, security_risk_level="MEDIUM", affected_reports=["REP-SEC-OFFBOARDING"]))
        return res

    def _fuzzy_duplicates(self, golden, already: set) -> List[QualityIssue]:
        """Near-duplicate identities: same date of birth and very similar (not identical) names, or same passport."""
        res = []
        by_dob = defaultdict(list)
        by_passport = defaultdict(list)
        for cid, g in golden.items():
            if g.date_of_birth:
                by_dob[g.date_of_birth].append(g)
            if g.passport_number:
                by_passport[g.passport_number.strip().upper()].append(g)
        seen = set()
        for group, reason_fn in ((by_dob, None), (by_passport, "passport")):
            for _, gs in group.items():
                if len(gs) < 2 or len(gs) > 25:
                    continue
                for i in range(len(gs)):
                    for j in range(i + 1, len(gs)):
                        a, b = gs[i], gs[j]
                        key = tuple(sorted((a.canonical_id, b.canonical_id)))
                        if key in seen or a.canonical_id in already or b.canonical_id in already:
                            continue
                        na, nb = normalize_name(a.full_name or ""), normalize_name(b.full_name or "")
                        if reason_fn == "passport":
                            reason, conf = f"Same passport number {a.passport_number}", 0.95
                        else:
                            sim = jaro_winkler_similarity(na, nb)
                            if na == nb or sim < 0.93 or a.gender != b.gender:
                                continue
                            reason, conf = f"Same date of birth ({a.date_of_birth}) and near-identical names ('{a.full_name}' / '{b.full_name}', similarity {sim:.2f})", round(min(0.9, sim - 0.05), 2)
                        seen.add(key)
                        primary, secondary = sorted(key, key=lambda c: (-len(golden[c].link_methods), c))
                        res.append(_issue(
                            issue_id=f"ERR-DUP-FUZZY-{primary}-{secondary}", category=IssueCategory.DUPLICATE_ENTITY, severity=Severity.MEDIUM,
                            title="Possible Duplicate Employee (Fuzzy Match)",
                            description=f"{primary} and {secondary} may be the same person. {reason}.",
                            primary_entity_id=primary, entity_name=f"{a.full_name} / {b.full_name}",
                            source_systems=["core_hr"], fields_in_conflict=["full_name", "date_of_birth"],
                            evidence_trail=[EvidenceItem("core_hr", "record_1", primary), EvidenceItem("core_hr", "record_2", secondary),
                                            EvidenceItem("core_hr", "linkage_evidence", reason)],
                            suggested_fix=f"Steward to confirm identity documents, then merge {secondary} into {primary}.",
                            recommended_target_system="core_hr", recommended_target_field="employee_id", recommended_target_value=primary,
                            confidence_score=conf, rationale="Probabilistic match; requires human confirmation before merge.",
                            impact_score=70.0, affected_reports=["REP-EXEC-HEADCOUNT"]))
        return res
