"""
Multi-Category Quality Anomaly & Conflict Detection Engine for VeritasHR.
Scans the unified Golden Record graph and raw source records to detect:
  1. Ghost Payroll Records (Direct Financial Leakage)
  2. Zombie IT Accounts (Security & Access Exposure)
  3. Department & Cost Center Conflicts
  4. Invalid Reference Codes (Schema Violations)
  5. Date Mismatches & Temporal Sequence Inconsistencies
  6. Duplicate Employee Identities
  7. Missing Mandatory Attributes
"""

import re
from datetime import datetime
from typing import Dict, List, Any, Set, Optional, Tuple
from src.models.issue import (
    QualityIssue,
    IssueCategory,
    Severity,
    EvidenceItem,
    GoldenEmployeeRecord,
    BlastRadiusNode
)
from src.ingestion.loader import ReferenceCatalog
from src.ingestion.schema_mapper import parse_any_date
from src.anomaly.extended_checks import ExtendedChecks, closest_code

def parse_date(date_str: str) -> Optional[datetime]:
    return parse_any_date(date_str)

class AnomalyDetector:
    def __init__(self, catalog: ReferenceCatalog, reference_date: Optional[datetime] = None):
        self.catalog = catalog
        self.reference_date = reference_date
        self.issues: List[QualityIssue] = []

    def detect_all_anomalies(
        self,
        golden_records: Dict[str, GoldenEmployeeRecord],
        sources: Dict[str, List[Dict[str, Any]]],
        duplicate_pairs: List[Tuple[str, str, str, float]],
        unlinked: Optional[Dict[str, List[Dict[str, Any]]]] = None,
        multi_links: Optional[Dict[str, Dict[str, List[Dict[str, Any]]]]] = None
    ) -> List[QualityIssue]:
        """Runs the full anomaly detection suite across the unified entity graph."""
        self.issues.clear()
        self._golden = golden_records
        if hasattr(self, "_peer_stats"):
            del self._peer_stats
        
        # 1. Process duplicate identities from entity resolution
        self._detect_duplicates(duplicate_pairs, golden_records)
        
        # 2. Check each golden record against cross-system rules
        for cid, grec in golden_records.items():
            self._check_ghost_payroll(grec)
            self._check_zombie_access(grec)
            self._check_department_and_cost_center(grec, sources)
            self._check_invalid_reference_codes(grec)
            self._check_date_inconsistencies(grec, sources)
            self._check_missing_mandatory_values(grec)

        # 3. Source records that match no Core HR employee at all
        self._detect_orphans(unlinked or {})

        # 4. Extended schema-generic checks (conflicts, dates, missing, validity, double links, staleness)
        secondaries = {b for _, b, _, _ in duplicate_pairs}
        ext = ExtendedChecks(self.catalog, self.reference_date)
        self.issues.extend(ext.run(golden_records, sources, self.issues, multi_links or {}, secondaries))

        return self.issues

    def _detect_orphans(self, unlinked: Dict[str, List[Dict[str, Any]]]):
        """Payroll payees or directory accounts with no matching employee in Core HR."""
        for pay in unlinked.get("payroll", []):
            if pay.get("pay_status") != "ACTIVE":
                continue
            pid = pay.get("payroll_id") or pay.get("employee_ref") or "UNKNOWN"
            try:
                salary = float(pay.get("monthly_basic_aed") or 0)
            except ValueError:
                salary = 0.0
            self.issues.append(QualityIssue(
                issue_id=f"ERR-ORPHAN-PAY-{pid}",
                category=IssueCategory.GHOST_RECORD,
                severity=Severity.CRITICAL,
                title="Active Payee With No Core HR Employee Record",
                description=(f"Payroll record {pid} ({pay.get('legal_name') or 'no name'}, ref '{pay.get('employee_ref') or '-'}') "
                             f"is ACTIVE and paid AED {salary:,.2f}/month, but no matching employee exists in Core HR by ID or name."),
                primary_entity_id=pay.get("employee_ref") or pid,
                entity_name=pay.get("legal_name") or "Unknown",
                source_systems=["payroll", "core_hr"],
                fields_in_conflict=["employee_ref"],
                evidence_trail=[
                    EvidenceItem(system_name="payroll", field_name="payroll_id", recorded_value=pid),
                    EvidenceItem(system_name="payroll", field_name="employee_ref", recorded_value=pay.get("employee_ref")),
                    EvidenceItem(system_name="payroll", field_name="legal_name", recorded_value=pay.get("legal_name")),
                    EvidenceItem(system_name="core_hr", field_name="match_search", recorded_value="No ID, normalized-ID or name match", is_authoritative=True),
                ],
                suggested_fix="Place payment on HOLD and verify the payee's identity with HR before next payroll run.",
                recommended_target_system="payroll",
                recommended_target_field="pay_status",
                recommended_target_value="HOLD",
                confidence_score=0.85,
                rationale="Every payee must correspond to an employee in Core HR, the system of record.",
                impact_score=95.0,
                financial_risk_aed=salary * 12,
                affected_reports=["REP-WPS-PAYROLL", "REP-EXEC-HEADCOUNT"]
            ))
        for ad in unlinked.get("access_directory", []):
            if ad.get("account_status") != "Active":
                continue
            acct = ad.get("samaccountname") or ad.get("employee_number") or "UNKNOWN"
            self.issues.append(QualityIssue(
                issue_id=f"ERR-ORPHAN-AD-{acct}",
                category=IssueCategory.SECURITY_EXPOSURE,
                severity=Severity.HIGH,
                title="Active Directory Account With No Core HR Employee",
                description=(f"Account '{acct}' ({ad.get('display_name') or 'no name'}) is Active, last logon "
                             f"{ad.get('last_logon_timestamp') or 'unknown'}, but no matching employee exists in Core HR."),
                primary_entity_id=ad.get("employee_number") or acct,
                entity_name=ad.get("display_name") or "Unknown",
                source_systems=["access_directory", "core_hr"],
                fields_in_conflict=["employee_number"],
                evidence_trail=[
                    EvidenceItem(system_name="access_directory", field_name="samaccountname", recorded_value=acct),
                    EvidenceItem(system_name="access_directory", field_name="employee_number", recorded_value=ad.get("employee_number")),
                    EvidenceItem(system_name="access_directory", field_name="account_status", recorded_value=ad.get("account_status")),
                    EvidenceItem(system_name="core_hr", field_name="match_search", recorded_value="No ID, normalized-ID or name match", is_authoritative=True),
                ],
                suggested_fix="Disable the account pending identity verification by the account owner's line manager.",
                recommended_target_system="access_directory",
                recommended_target_field="account_status",
                recommended_target_value="Disabled",
                confidence_score=0.85,
                rationale="Directory accounts must be provisioned from a Core HR employee record.",
                impact_score=88.0,
                security_risk_level="HIGH",
                affected_reports=["REP-SEC-OFFBOARDING"]
            ))

    def _detect_duplicates(
        self,
        duplicate_pairs: List[Tuple[str, str, str, float]],
        golden_records: Dict[str, GoldenEmployeeRecord]
    ):
        for id1, id2, reason, conf in duplicate_pairs:
            g1 = golden_records.get(id1)
            g2 = golden_records.get(id2)
            name1 = g1.full_name if g1 else id1
            name2 = g2.full_name if g2 else id2
            
            issue = QualityIssue(
                issue_id=f"ERR-DUP-{id1}-{id2}",
                category=IssueCategory.DUPLICATE_ENTITY,
                severity=Severity.HIGH,
                title="Duplicate Employee Records Detected",
                description=f"Duplicate entity detected between {id1} ({name1}) and {id2} ({name2}). Reason: {reason}.",
                primary_entity_id=id1,
                entity_name=f"{name1} / {name2}",
                source_systems=["core_hr"],
                fields_in_conflict=["employee_id", "national_id", "first_name"],
                evidence_trail=[
                    EvidenceItem(system_name="core_hr", field_name="record_1", recorded_value=id1),
                    EvidenceItem(system_name="core_hr", field_name="record_2", recorded_value=id2),
                    EvidenceItem(system_name="core_hr", field_name="linkage_evidence", recorded_value=reason)
                ],
                suggested_fix=f"Merge duplicate profile {id2} into master employee profile {id1}.",
                recommended_target_system="core_hr",
                recommended_target_field="employee_id",
                recommended_target_value=id1,
                confidence_score=conf,
                rationale=f"High-confidence entity resolution match based on {reason}.",
                impact_score=82.0,
                affected_reports=["REP-EXEC-HEADCOUNT"],
                security_risk_level="MEDIUM"
            )
            self.issues.append(issue)

    def _check_ghost_payroll(self, grec: GoldenEmployeeRecord):
        """Terminated in Core HR, but active on Payroll receiving monthly salary."""
        if grec.employment_status in ("TERMINATED", "RESIGNED") and grec.pay_status == "ACTIVE":
            salary = grec.monthly_basic_aed or 15000.0
            annual_leakage = salary * 12
            
            issue = QualityIssue(
                issue_id=f"ERR-GHOST-{grec.canonical_id}",
                category=IssueCategory.GHOST_RECORD,
                severity=Severity.CRITICAL,
                title="Ghost Employee Receiving Active Payroll",
                description=(
                    f"Employee {grec.canonical_id} was {grec.employment_status} in Core HR "
                    f"(effective {grec.termination_date or 'N/A'}) but remains ACTIVE in Payroll "
                    f"disbursing AED {salary:,.2f} per month."
                ),
                primary_entity_id=grec.canonical_id,
                entity_name=grec.full_name or "Unknown",
                source_systems=["core_hr", "payroll"],
                fields_in_conflict=["employment_status", "pay_status"],
                evidence_trail=[
                    EvidenceItem(system_name="core_hr", field_name="employment_status", recorded_value=grec.employment_status, is_authoritative=True),
                    EvidenceItem(system_name="core_hr", field_name="termination_date", recorded_value=grec.termination_date),
                    EvidenceItem(system_name="payroll", field_name="pay_status", recorded_value=grec.pay_status),
                    EvidenceItem(system_name="payroll", field_name="monthly_basic_aed", recorded_value=salary)
                ],
                suggested_fix="Update payroll.pay_status to 'INACTIVE' and initiate payroll recovery audit.",
                recommended_target_system="payroll",
                recommended_target_field="pay_status",
                recommended_target_value="INACTIVE",
                confidence_score=0.99,
                rationale="Core HR is the authoritative System of Record for employment lifecycle events.",
                impact_score=98.0,
                financial_risk_aed=annual_leakage,
                security_risk_level="LOW",
                affected_reports=["REP-WPS-PAYROLL", "REP-EXEC-HEADCOUNT"]
            )
            self.issues.append(issue)

    def _check_zombie_access(self, grec: GoldenEmployeeRecord):
        """Terminated in Core HR, but Active Directory account remains Active."""
        if grec.employment_status in ("TERMINATED", "RESIGNED") and grec.ad_account_status == "Active":
            last_login = grec.last_logon_timestamp or "Unknown"
            
            issue = QualityIssue(
                issue_id=f"ERR-ZOMBIE-{grec.canonical_id}",
                category=IssueCategory.SECURITY_EXPOSURE,
                severity=Severity.HIGH,
                title="Terminated Employee Retaining Active IT Directory Access",
                description=(
                    f"Terminated employee {grec.canonical_id} (exited {grec.termination_date or 'N/A'}) "
                    f"still has an 'Active' Active Directory account ({grec.directory_id}) with recent login: {last_login}."
                ),
                primary_entity_id=grec.canonical_id,
                entity_name=grec.full_name or "Unknown",
                source_systems=["core_hr", "access_directory"],
                fields_in_conflict=["employment_status", "account_status"],
                evidence_trail=[
                    EvidenceItem(system_name="core_hr", field_name="employment_status", recorded_value=grec.employment_status, is_authoritative=True),
                    EvidenceItem(system_name="core_hr", field_name="termination_date", recorded_value=grec.termination_date),
                    EvidenceItem(system_name="access_directory", field_name="account_status", recorded_value=grec.ad_account_status),
                    EvidenceItem(system_name="access_directory", field_name="last_logon_timestamp", recorded_value=last_login)
                ],
                suggested_fix="Immediately disable AD account and revoke physical airside badge access.",
                recommended_target_system="access_directory",
                recommended_target_field="account_status",
                recommended_target_value="Disabled",
                confidence_score=0.99,
                rationale="Core HR termination triggers mandatory automated IT offboarding.",
                impact_score=92.0,
                security_risk_level="CRITICAL",
                affected_reports=["REP-SEC-OFFBOARDING"]
            )
            self.issues.append(issue)

    def _check_department_and_cost_center(self, grec: GoldenEmployeeRecord, sources: Dict[str, List[Dict[str, Any]]]):
        """Department in Core HR does not match Payroll Cost Center or LMS."""
        if not grec.payroll_id:
            return

        cost_center = grec.payroll_cost_center or ""
        expected_cc = f"CC-{grec.department_code}"

        if cost_center and expected_cc != cost_center.strip().upper() and cost_center.strip().upper() != grec.department_code and grec.department_code in self.catalog.departments:
            issue = QualityIssue(
                issue_id=f"ERR-DEPT-{grec.canonical_id}",
                category=IssueCategory.DEPARTMENT_CONFLICT,
                severity=Severity.MEDIUM,
                title="Department & Payroll Cost Center Mismatch",
                description=(
                    f"Core HR assigns employee {grec.canonical_id} to '{grec.department_code}', "
                    f"but Payroll is charging cost center '{cost_center}'."
                ),
                primary_entity_id=grec.canonical_id,
                entity_name=grec.full_name or "Unknown",
                source_systems=["core_hr", "payroll"],
                fields_in_conflict=["department_code", "cost_center"],
                evidence_trail=[
                    EvidenceItem(system_name="core_hr", field_name="department_code", recorded_value=grec.department_code, is_authoritative=True),
                    EvidenceItem(system_name="payroll", field_name="cost_center", recorded_value=cost_center)
                ],
                suggested_fix=f"Update payroll.cost_center to '{expected_cc}'.",
                recommended_target_system="payroll",
                recommended_target_field="cost_center",
                recommended_target_value=expected_cc,
                confidence_score=0.95,
                rationale="Core HR is the primary System of Record for organizational assignments.",
                impact_score=68.0,
                affected_reports=["REP-EXEC-HEADCOUNT", "REP-LMS-BUDGET"]
            )
            self.issues.append(issue)

    def _check_invalid_reference_codes(self, grec: GoldenEmployeeRecord):
        """Validates department, grade, and location against the reference catalog."""
        # Department check
        if grec.department_code and grec.department_code not in self.catalog.departments:
            # Fuzzy suggest closest
            valid_list = sorted(self.catalog.departments)
            suggested, conf, basis = self._suggest_code(grec, "department_code", self.catalog.departments)
            
            issue = QualityIssue(
                issue_id=f"ERR-CODE-DEPT-{grec.canonical_id}",
                category=IssueCategory.INVALID_CODE,
                severity=Severity.MEDIUM,
                title="Invalid Department Reference Code",
                description=f"Department code '{grec.department_code}' is not a valid Emirates Group organizational code.",
                primary_entity_id=grec.canonical_id,
                entity_name=grec.full_name or "Unknown",
                source_systems=["core_hr"],
                fields_in_conflict=["department_code"],
                evidence_trail=[
                    EvidenceItem(system_name="core_hr", field_name="department_code", recorded_value=grec.department_code),
                    EvidenceItem(system_name="data_dictionary", field_name="allowed_departments", recorded_value=", ".join(valid_list[:5]) + "..."),
                    EvidenceItem(system_name="veritas_suggestion", field_name="basis", recorded_value=basis)
                ],
                suggested_fix=f"Standardize department_code to '{suggested}' ({basis}).",
                recommended_target_system="core_hr",
                recommended_target_field="department_code",
                recommended_target_value=suggested,
                confidence_score=conf,
                rationale=f"Value violates the data dictionary code list. Suggested value: {basis}.",
                impact_score=65.0,
                affected_reports=["REP-EXEC-HEADCOUNT"]
            )
            self.issues.append(issue)

        # Grade check
        if grec.job_grade and grec.job_grade not in self.catalog.job_grades:
            g_sug, g_conf, g_basis = self._suggest_code(grec, "job_grade", self.catalog.job_grades)
            issue = QualityIssue(
                issue_id=f"ERR-CODE-GRADE-{grec.canonical_id}",
                category=IssueCategory.INVALID_CODE,
                severity=Severity.MEDIUM,
                title="Invalid Job Grade Code",
                description=f"Job grade '{grec.job_grade}' does not conform to standardized pay scale tiers (G01-G12, CR01-CR06, T01-T08, E01-E05).",
                primary_entity_id=grec.canonical_id,
                entity_name=grec.full_name or "Unknown",
                source_systems=["core_hr"],
                fields_in_conflict=["job_grade"],
                evidence_trail=[
                    EvidenceItem(system_name="core_hr", field_name="job_grade", recorded_value=grec.job_grade)
                ],
                suggested_fix=f"Change job grade to '{g_sug}' after checking the contract ({g_basis}).",
                recommended_target_system="core_hr",
                recommended_target_field="job_grade",
                recommended_target_value=g_sug,
                confidence_score=g_conf,
                rationale="Invalid grade breaks automated salary band indexing.",
                impact_score=62.0,
                affected_reports=["REP-EXEC-HEADCOUNT", "REP-LMS-BUDGET"]
            )
            self.issues.append(issue)

        # Location check
        if grec.work_location and grec.work_location not in self.catalog.locations:
            l_sug, l_conf, l_basis = self._suggest_code(grec, "work_location", self.catalog.locations)
            issue = QualityIssue(
                issue_id=f"ERR-CODE-LOC-{grec.canonical_id}",
                category=IssueCategory.INVALID_CODE,
                severity=Severity.LOW,
                title="Invalid Work Location Code",
                description=f"Location '{grec.work_location}' is not a recognized operational station code.",
                primary_entity_id=grec.canonical_id,
                entity_name=grec.full_name or "Unknown",
                source_systems=["core_hr"],
                fields_in_conflict=["work_location"],
                evidence_trail=[
                    EvidenceItem(system_name="core_hr", field_name="work_location", recorded_value=grec.work_location)
                ],
                suggested_fix=f"Change work location to '{l_sug}' ({l_basis}).",
                recommended_target_system="core_hr",
                recommended_target_field="work_location",
                recommended_target_value=l_sug,
                confidence_score=l_conf,
                rationale="Station code violates IATA / Emirates location naming standard.",
                impact_score=45.0,
                affected_reports=["REP-EXEC-HEADCOUNT"]
            )
            self.issues.append(issue)

    def _peer_mode(self, field: str, job_title: Optional[str], valid: set):
        """Most common valid value of `field` among colleagues with the same job title."""
        if not hasattr(self, "_peer_stats"):
            self._peer_stats = {}
            for g in self._golden.values():
                for f in ("department_code", "job_grade", "work_location"):
                    v = getattr(g, f, None)
                    if v and g.job_title:
                        self._peer_stats.setdefault((f, g.job_title), {}).setdefault(v, 0)
                        self._peer_stats[(f, g.job_title)][v] += 1
        counts = {k: n for k, n in self._peer_stats.get((field, job_title), {}).items() if k in valid}
        if not counts:
            return None, 0.0, 0
        best = max(counts, key=counts.get)
        return best, counts[best] / sum(counts.values()), sum(counts.values())

    def _suggest_code(self, grec: GoldenEmployeeRecord, field: str, valid: set):
        """Most likely correct code with its basis: clear misspelling > other systems agree > colleagues > closest spelling."""
        value = getattr(grec, field) or ""
        sp, sp_score = closest_code(value, sorted(valid), getattr(self.catalog, "code_descriptions", {}))
        if sp and sp_score >= 0.8:
            return sp, round(0.6 + 0.35 * sp_score, 2), f"'{value}' is a near-spelling of valid code '{sp}' ({sp_score:.0%} similar)"
        if field == "department_code":
            votes: Dict[str, List[str]] = {}
            cc = (grec.payroll_cost_center or "").strip().upper()
            if cc.startswith("CC-") and cc[3:] in valid:
                votes.setdefault(cc[3:], []).append("payroll.cost_center")
            lms = (grec.learning_department or "").strip().upper()
            if lms in valid:
                votes.setdefault(lms, []).append("learning.assigned_department")
            if votes:
                best = max(votes, key=lambda k: len(votes[k]))
                return best, (0.92 if len(votes[best]) >= 2 else 0.85), f"value held by {' and '.join(votes[best])}"
        peer, share, n = self._peer_mode(field, grec.job_title, valid)
        if peer and n >= 5 and share >= 0.5:
            return peer, round(0.55 + 0.35 * share, 2), f"{share:.0%} of {n} colleagues with job title '{grec.job_title}' have '{peer}'"
        return sp, round(0.4 + 0.4 * sp_score, 2), f"closest valid code by spelling ({sp_score:.0%} similar)"

    def _check_date_inconsistencies(self, grec: GoldenEmployeeRecord, sources: Dict[str, List[Dict[str, Any]]]):
        """Detects date sequence conflicts between Core HR and Payroll."""
        if not grec.payroll_id:
            return

        pr_start_str = grec.payroll_effective_start_date
        pr_start = parse_date(grec.payroll_effective_start_iso or pr_start_str)
        hr_hire = parse_date(grec.hire_date)
        
        if pr_start and hr_hire:
            # If payroll start date differs from Core HR hire date by > 1 year
            diff_days = abs((pr_start - hr_hire).days)
            if diff_days > 365:
                issue = QualityIssue(
                    issue_id=f"ERR-DATE-{grec.canonical_id}",
                    category=IssueCategory.DATE_MISMATCH,
                    severity=Severity.MEDIUM,
                    title="Hire Date vs Payroll Effective Date Discrepancy",
                    description=(
                        f"Payroll start date ({pr_start_str}) differs by {diff_days // 365} years from "
                        f"Core HR hire date ({grec.hire_date})."
                    ),
                    primary_entity_id=grec.canonical_id,
                    entity_name=grec.full_name or "Unknown",
                    source_systems=["core_hr", "payroll"],
                    fields_in_conflict=["hire_date", "effective_start_date"],
                    evidence_trail=[
                        EvidenceItem(system_name="core_hr", field_name="hire_date", recorded_value=grec.hire_date, is_authoritative=True),
                        EvidenceItem(system_name="payroll", field_name="effective_start_date", recorded_value=pr_start_str)
                    ],
                    suggested_fix=f"Align payroll effective start date to Core HR hire date: {hr_hire.strftime('%d/%m/%Y')}.",
                    recommended_target_system="payroll",
                    recommended_target_field="effective_start_date",
                    recommended_target_value=hr_hire.strftime('%d/%m/%Y'),
                    confidence_score=0.95,
                    rationale="Employment commencement dates in Payroll must synchronize with Core HR.",
                    impact_score=60.0,
                    affected_reports=["REP-WPS-PAYROLL", "REP-EXEC-HEADCOUNT"]
                )
                self.issues.append(issue)

    def _check_missing_mandatory_values(self, grec: GoldenEmployeeRecord):
        """Detects missing critical fields such as IBAN for active payroll."""
        if grec.pay_status == "ACTIVE" and (not grec.bank_iban or len(grec.bank_iban.strip()) < 15):
            issue = QualityIssue(
                issue_id=f"ERR-NOIBAN-{grec.canonical_id}",
                category=IssueCategory.MISSING_VALUE,
                severity=Severity.HIGH,
                title="Missing Bank IBAN on Active Payroll Record",
                description=f"Employee {grec.canonical_id} is active on payroll but has no valid bank IBAN recorded.",
                primary_entity_id=grec.canonical_id,
                entity_name=grec.full_name or "Unknown",
                source_systems=["payroll"],
                fields_in_conflict=["bank_iban"],
                evidence_trail=[
                    EvidenceItem(system_name="payroll", field_name="bank_iban", recorded_value="[EMPTY]"),
                    EvidenceItem(system_name="payroll", field_name="pay_status", recorded_value=grec.pay_status)
                ],
                suggested_fix="Collect employee bank account details prior to monthly payroll cutoff.",
                recommended_target_system="payroll",
                recommended_target_field="bank_iban",
                recommended_target_value="[AWAITING_INPUT]",
                confidence_score=0.99,
                rationale="WPS salary disbursement strictly mandates a valid UAE Central Bank format IBAN.",
                impact_score=85.0,
                affected_reports=["REP-WPS-PAYROLL"]
            )
            self.issues.append(issue)
