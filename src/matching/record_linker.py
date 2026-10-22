"""
Entity Resolution & Cross-System Identity Matching Engine for VeritasHR.
Performs deterministic blocking and probabilistic fuzzy matching across disparate HR applications.
"""

import re
from typing import Dict, List, Any, Tuple, Optional
from collections import defaultdict
from src.models.issue import GoldenEmployeeRecord
from src.ingestion.schema_mapper import normalize_id

def normalize_name(name: str) -> str:
    """Normalizes names by stripping honorifics, punctuation, and standardizing case."""
    if not name:
        return ""
    name = name.lower()
    # Handle "LAST, FIRST" format
    if "," in name:
        parts = [p.strip() for p in name.split(",", 1)]
        name = f"{parts[1]} {parts[0]}"
    name = re.sub(r"[^a-z\s]", "", name)
    return " ".join(name.split())

def jaro_winkler_similarity(s1: str, s2: str) -> float:
    """
    Pure Python high-speed implementation of Jaro-Winkler similarity.
    Provides robust string similarity even without external C-extensions.
    """
    if s1 == s2:
        return 1.0
    len1, len2 = len(s1), len(s2)
    if len1 == 0 or len2 == 0:
        return 0.0

    max_dist = max(len1, len2) // 2 - 1
    if max_dist < 0:
        max_dist = 0

    s1_matches = [False] * len1
    s2_matches = [False] * len2
    matches = 0

    for i in range(len1):
        start = max(0, i - max_dist)
        end = min(i + max_dist + 1, len2)
        for j in range(start, end):
            if s2_matches[j] or s1[i] != s2[j]:
                continue
            s1_matches[i] = True
            s2_matches[j] = True
            matches += 1
            break

    if matches == 0:
        return 0.0

    transpositions = 0
    k = 0
    for i in range(len1):
        if not s1_matches[i]:
            continue
        while not s2_matches[k]:
            k += 1
        if s1[i] != s2[k]:
            transpositions += 1
        k += 1

    jaro = (
        (matches / len1) +
        (matches / len2) +
        ((matches - transpositions / 2) / matches)
    ) / 3.0

    # Winkler prefix bonus (up to 4 characters)
    prefix = 0
    for i in range(min(4, len1, len2)):
        if s1[i] == s2[i]:
            prefix += 1
        else:
            break

    return jaro + prefix * 0.1 * (1.0 - jaro)

class EntityResolver:
    def __init__(self):
        self.golden_records: Dict[str, GoldenEmployeeRecord] = {}
        self.duplicate_pairs: List[Tuple[str, str, str, float]] = [] # (id1, id2, reason, confidence)
        self.unlinked: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        
    def resolve_identities(self, sources: Dict[str, List[Dict[str, Any]]]) -> Dict[str, GoldenEmployeeRecord]:
        """
        Unifies disparate records into canonical GoldenEmployeeRecord entities.
        Links records across:
          - Core HR (Master)
          - Payroll
          - Learning LMS
          - Access Directory
        """
        core_records = sources.get("core_hr", [])
        payroll_records = sources.get("payroll", [])
        learning_records = sources.get("learning", [])
        directory_records = sources.get("access_directory", [])

        # Step 1: Initialize Golden Records from Core HR
        national_id_index: Dict[str, str] = {}
        dob_name_index: Dict[Tuple[str, str], str] = {}

        for emp in core_records:
            cid = emp["employee_id"]
            first = emp.get("first_name", "")
            last = emp.get("last_name", "")
            full_name = f"{first} {last}".strip()
            norm_name = normalize_name(full_name)
            nat_id = emp.get("national_id", "")
            dob = emp.get("date_of_birth", "")

            # Check for intra-system duplicate in Core HR
            if nat_id and nat_id in national_id_index:
                primary_id = national_id_index[nat_id]
                self.duplicate_pairs.append((
                    primary_id, cid,
                    f"Identical National ID: {nat_id}",
                    1.0
                ))
            elif nat_id:
                national_id_index[nat_id] = cid

            if dob and norm_name:
                dob_key = (dob, norm_name)
                if dob_key in dob_name_index:
                    primary_id = dob_name_index[dob_key]
                    if primary_id != cid:
                        self.duplicate_pairs.append((
                            primary_id, cid,
                            f"Identical Date of Birth ({dob}) and Name ({full_name})",
                            0.95
                        ))
                else:
                    dob_name_index[dob_key] = cid

            # Instantiate Golden Record
            self.golden_records[cid] = GoldenEmployeeRecord(
                canonical_id=cid,
                core_hr_id=cid,
                first_name=first,
                last_name=last,
                full_name=full_name,
                date_of_birth=dob,
                gender=emp.get("gender"),
                nationality=emp.get("nationality"),
                national_id=nat_id,
                passport_number=emp.get("passport_number"),
                department_code=emp.get("department_code"),
                job_title=emp.get("job_title"),
                job_grade=emp.get("job_grade"),
                work_location=emp.get("work_location"),
                employment_status=emp.get("employment_status"),
                hire_date=emp.get("hire_date"),
                termination_date=emp.get("termination_date") if emp.get("termination_date") else None
            )

        self._build_link_indexes()

        # Step 2: Link Payroll Records
        def payroll_keys(pay):
            cc = (pay.get("cost_center") or "").upper()
            return pay.get("employee_ref"), pay.get("legal_name"), {
                "hire_date": pay.get("effective_start_date_iso"),
                "department_code": cc[3:] if cc.startswith("CC-") else cc,
                "date_of_birth": pay.get("date_of_birth"),
            }
        for pay, target_record in self._link_all(payroll_records, "payroll", payroll_keys):
                target_record.payroll_id = pay.get("payroll_id")
                try:
                    target_record.monthly_basic_aed = float(pay.get("monthly_basic_aed") or 0)
                except (ValueError, TypeError):
                    target_record.monthly_basic_aed = 0.0
                target_record.bank_iban = pay.get("bank_iban")
                target_record.pay_status = pay.get("pay_status")
                target_record.payroll_cost_center = pay.get("cost_center")
                target_record.payroll_effective_start_date = pay.get("effective_start_date")
                target_record.payroll_effective_start_iso = pay.get("effective_start_date_iso")

        # Step 3: Link Learning LMS Records
        def learning_keys(lms):
            return lms.get("emp_core_id"), lms.get("full_name"), {
                "department_code": (lms.get("assigned_department") or "").upper(),
                "job_title": lms.get("job_role"),
            }
        for lms, target_record in self._link_all(learning_records, "learning", learning_keys):
                target_record.learning_id = lms.get("lms_user_id")
                target_record.aviation_safety_cert = lms.get("aviation_safety_cert")
                target_record.training_compliance_status = lms.get("compliance_status")
                target_record.learning_department = lms.get("assigned_department")
                target_record.learning_job_role = lms.get("job_role")

        # Step 4: Link Access Directory (IAM) Records
        def directory_keys(ad):
            raw_disp = ad.get("display_name", "") or ""
            dept_hint = re.search(r"\(([^)]+)\)", raw_disp)
            return ad.get("employee_number"), re.sub(r"\(.*?\)", "", raw_disp), {
                "department_code": dept_hint.group(1).upper() if dept_hint else None,
            }
        for ad, target_record in self._link_all(directory_records, "access_directory", directory_keys):
                target_record.directory_id = ad.get("samaccountname")
                target_record.work_email = ad.get("work_email")
                target_record.ad_account_status = ad.get("account_status")
                target_record.last_logon_timestamp = ad.get("last_logon_timestamp")

        return self.golden_records

    def _build_link_indexes(self):
        """Builds exact, normalized-ID, numeric-ID and name indexes over Core HR golden records."""
        self.unlinked: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self.multi_links: Dict[str, Dict[str, List[Dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
        self._claimed: Dict[str, set] = {}
        self._norm_id_index: Dict[str, str] = {}
        digit_index: Dict[str, List[str]] = defaultdict(list)
        name_index: Dict[str, List[str]] = defaultdict(list)
        for cid, grec in self.golden_records.items():
            self._norm_id_index.setdefault(normalize_id(cid), cid)
            digits = re.sub(r"\D", "", cid).lstrip("0")
            if digits:
                digit_index[digits].append(cid)
            nm = normalize_name(grec.full_name or "")
            if nm:
                name_index[nm].append(cid)
        # Only keep unambiguous numeric / name keys
        self._digit_index = {k: v[0] for k, v in digit_index.items() if len(v) == 1}
        self._name_index = {k: v[0] for k, v in name_index.items() if len(v) == 1}
        self._name_groups = dict(name_index)
        self._names = [(normalize_name(g.full_name or ""), cid) for cid, g in self.golden_records.items()]

    def _link_all(self, records: List[Dict[str, Any]], system: str, key_fn):
        """Two-pass linking: ID-bearing records first, then name-only records against the people still unclaimed."""
        leftovers = []
        self._claimed.setdefault(system, set())
        for rec in records:
            ref, name, hints = key_fn(rec)
            grec = self._link(ref, name, system, rec, hints, id_only=True)
            if grec and grec.canonical_id in self._claimed[system]:
                self.multi_links[system][grec.canonical_id].append(rec)
            elif grec:
                self._claimed[system].add(grec.canonical_id)
                grec.source_names[system] = name or ""
                yield rec, grec
            else:
                leftovers.append(rec)
        for rec in leftovers:
            ref, name, hints = key_fn(rec)
            grec = self._link(ref, name, system, rec, hints)
            if grec and grec.canonical_id in self._claimed[system]:
                self.multi_links[system][grec.canonical_id].append(rec)
            elif grec:
                self._claimed[system].add(grec.canonical_id)
                grec.source_names[system] = name or ""
                yield rec, grec

    def _corroboration(self, grec: GoldenEmployeeRecord, hints: Dict[str, Any]) -> int:
        """Counts secondary attributes (dates, department, job) that agree with a candidate."""
        score = 0
        for f, v in (hints or {}).items():
            if v and str(getattr(grec, f, "") or "").strip().lower() == str(v).strip().lower():
                score += 1
        return score

    def _link(self, ref: Optional[str], name: Optional[str], system: str, raw: Dict[str, Any],
              hints: Optional[Dict[str, Any]] = None, id_only: bool = False) -> Optional[GoldenEmployeeRecord]:
        """Links one source record to a golden record: exact ID -> normalized ID -> numeric ID -> name (+corroboration)."""
        method, cid = None, None
        if ref and ref in self.golden_records:
            method, cid = "exact_id", ref
        elif ref and normalize_id(ref) in self._norm_id_index:
            method, cid = "normalized_id", self._norm_id_index[normalize_id(ref)]
        elif ref and re.sub(r"\D", "", ref).lstrip("0") in self._digit_index:
            method, cid = "numeric_id", self._digit_index[re.sub(r"\D", "", ref).lstrip("0")]
        elif id_only:
            return None
        else:
            nm = normalize_name(name or "")
            if nm and nm in self._name_index:
                method, cid = "exact_name", self._name_index[nm]
            elif nm in self._name_groups:
                # Same name shared by several employees: pick the one other attributes agree with
                ranked = sorted(((self._corroboration(self.golden_records[c], hints), c) for c in self._name_groups[nm]
                                 if system not in self.golden_records[c].link_methods), reverse=True)
                if len(ranked) == 1:
                    method, cid = "name+elimination", ranked[0][1]
                elif ranked and ranked[0][0] > 0 and ranked[0][0] > ranked[1][0]:
                    method, cid = f"name+corroboration:{ranked[0][0]}", ranked[0][1]
            elif nm:
                cands = []
                for cand, c in self._names:
                    if not cand or cand[0] != nm[0] or system in self.golden_records[c].link_methods:
                        continue
                    sim = jaro_winkler_similarity(nm, cand)
                    if sim > 0.90:
                        cands.append((sim + 0.05 * self._corroboration(self.golden_records[c], hints), sim, c))
                if cands:
                    cands.sort(reverse=True)
                    top, sim, c = cands[0]
                    if top > 0.94 and (len(cands) == 1 or top - cands[1][0] > 0.02):
                        method, cid = f"fuzzy_name:{sim:.2f}", c
        if not cid:
            self.unlinked[system].append(raw)
            return None
        grec = self.golden_records[cid]
        grec.link_methods[system] = method
        if method != "exact_id":
            conf = 0.95 if "id" in method else 0.85
            grec.linkage_confidence = min(grec.linkage_confidence, conf)
        return grec
