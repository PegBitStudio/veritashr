"""
Schema auto-mapping for VeritasHR.
Maps whatever column names and value formats a source file uses onto VeritasHR's
canonical schema, so new or renamed HR sources can be onboarded without code changes.

Resolution order per canonical field:
  1. Explicit override from <data_dir>/schema_mapping.json (steward-pinned)
  2. Header alias match (case/punctuation-insensitive)
  3. Content sniffing (value patterns such as IBAN, e-mail, national ID)
Every decision is recorded in a mapping report so the steward can audit it.
"""

import os
import re
import json
from datetime import datetime
from typing import Dict, List, Any, Optional, Callable, Tuple

def norm_header(h: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (h or "").lower())

# Canonical field -> header aliases (compared after norm_header)
CANONICAL_SCHEMAS: Dict[str, Dict[str, List[str]]] = {
    "core_hr": {
        "employee_id": ["employee_id", "emp_id", "employeeid", "employee_number", "emp_no", "staff_id", "staff_no", "person_id", "worker_id", "id"],
        "first_name": ["first_name", "firstname", "given_name", "forename", "fname"],
        "last_name": ["last_name", "lastname", "surname", "family_name", "lname"],
        "full_name": ["full_name", "fullname", "employee_name", "name", "display_name", "legal_name"],
        "date_of_birth": ["date_of_birth", "dob", "birth_date", "birthdate"],
        "gender": ["gender", "sex"],
        "nationality": ["nationality", "citizenship", "country_of_citizenship", "nationality_code"],
        "national_id": ["national_id", "emirates_id", "eid", "nationalid", "emiratesid", "national_id_number"],
        "passport_number": ["passport_number", "passport_no", "passport"],
        "department_code": ["department_code", "dept_code", "department", "dept", "org_unit", "division", "department_id"],
        "job_title": ["job_title", "title", "position", "position_title", "role", "job_role"],
        "job_grade": ["job_grade", "grade", "pay_grade", "band", "job_level", "grade_code"],
        "work_location": ["work_location", "location", "location_code", "station", "base", "work_site"],
        "employment_status": ["employment_status", "status", "emp_status", "employee_status", "hr_status"],
        "hire_date": ["hire_date", "date_of_joining", "doj", "join_date", "start_date", "joining_date", "date_hired"],
        "termination_date": ["termination_date", "term_date", "leaving_date", "exit_date", "end_date", "separation_date", "last_working_day"],
    },
    "payroll": {
        "payroll_id": ["payroll_id", "pay_id", "payroll_number", "payroll_no", "pr_id"],
        "employee_ref": ["employee_ref", "employee_id", "emp_id", "emp_ref", "employee_number", "emp_no", "staff_id", "staff_no", "staff_number", "hr_id", "core_id", "person_id"],
        "legal_name": ["legal_name", "full_name", "employee_name", "name", "payee_name"],
        "bank_iban": ["bank_iban", "iban", "iban_number", "bank_account"],
        "bank_name": ["bank_name", "bank"],
        "monthly_basic_aed": ["monthly_basic_aed", "basic_salary", "monthly_basic", "salary", "basic_pay", "monthly_salary", "base_salary"],
        "currency": ["currency", "ccy"],
        "cost_center": ["cost_center", "cost_centre", "costcenter", "cc", "cost_center_code"],
        "pay_status": ["pay_status", "payroll_status", "status", "payment_status"],
        "effective_start_date": ["effective_start_date", "effective_date", "start_date", "pay_start_date", "payroll_start_date", "hire_date"],
    },
    "learning": {
        "lms_user_id": ["lms_user_id", "lms_id", "learner_id", "user_id"],
        "emp_core_id": ["emp_core_id", "employee_id", "emp_id", "employee_ref", "employee_number", "emp_no", "hr_id", "core_id", "staff_id", "staff_no", "staff_number", "person_id"],
        "full_name": ["full_name", "name", "learner_name", "employee_name", "display_name"],
        "assigned_department": ["assigned_department", "department", "department_code", "dept", "dept_code"],
        "job_role": ["job_role", "job_title", "role", "job_code", "position"],
        "aviation_safety_cert": ["aviation_safety_cert", "safety_cert", "certification", "gcaa_cert", "cert_status", "license"],
        "last_training_date": ["last_training_date", "training_date", "last_completed", "completion_date"],
        "compliance_status": ["compliance_status", "compliance", "training_status"],
    },
    "access_directory": {
        "samaccountname": ["samaccountname", "username", "user_name", "login", "account_name", "user_id", "upn"],
        "work_email": ["work_email", "email", "mail", "email_address"],
        "employee_number": ["employee_number", "employee_id", "emp_id", "employee_ref", "emp_no", "hr_id", "staff_id", "staff_no", "staff_number", "employeeid", "person_id"],
        "display_name": ["display_name", "displayname", "full_name", "name", "cn"],
        "account_status": ["account_status", "status", "enabled", "account_enabled", "user_status"],
        "badge_id": ["badge_id", "badge", "badge_number", "access_card"],
        "last_logon_timestamp": ["last_logon_timestamp", "last_logon", "lastlogon", "last_login", "lastlogontimestamp", "last_sign_in"],
    },
}

# Last-resort header keywords for fields whose header matched no alias (e.g. "Shift Status", "Joined On")
TOKEN_HINTS: Dict[str, List[str]] = {
    "employment_status": ["status"], "pay_status": ["status"], "account_status": ["status", "enabled"],
    "hire_date": ["join", "hire", "start"], "termination_date": ["leav", "exit", "termin", "separat"],
    "date_of_birth": ["birth", "dob"], "department_code": ["dept", "depart", "division"],
    "job_title": ["title", "position", "role", "designation"], "work_location": ["location", "station", "site", "base"],
    "job_grade": ["grade", "band", "level"], "full_name": ["name"], "legal_name": ["name"], "display_name": ["name"],
    "monthly_basic_aed": ["salary", "basic"], "cost_center": ["cost"], "bank_iban": ["iban"], "work_email": ["mail"],
}

# File discovery: system -> filename keyword hints (checked in order)
FILE_HINTS: Dict[str, List[str]] = {
    "core_hr": ["core_hr", "corehr", "core", "hris", "master", "employee"],
    "payroll": ["payroll", "pay", "salary", "wps"],
    "learning": ["learning", "lms", "training"],
    "access_directory": ["access_directory", "access", "directory", "ad_", "iam", "identity"],
}

DATE_FIELDS = {
    "core_hr": ["date_of_birth", "hire_date", "termination_date"],
    "payroll": ["effective_start_date"],
    "learning": ["last_training_date"],
    "access_directory": [],
}

# Value-pattern sniffers for fields whose header could not be matched
_SNIFFERS: Dict[str, Callable[[str], bool]] = {
    "bank_iban": lambda v: bool(re.fullmatch(r"AE\d{2}[A-Z0-9]{3,}\d*", v.replace(" ", "").upper())),
    "work_email": lambda v: bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[a-z]{2,}", v.lower())),
    "national_id": lambda v: bool(re.fullmatch(r"784-?\d{4}-?\d{7}-?\d", v)),
}

# Status synonyms -> canonical value per system
STATUS_MAPS: Dict[str, Dict[str, str]] = {
    "employment_status": {
        "active": "ACTIVE", "a": "ACTIVE", "employed": "ACTIVE", "current": "ACTIVE",
        "onleave": "ON_LEAVE", "leave": "ON_LEAVE", "loa": "ON_LEAVE",
        "terminated": "TERMINATED", "term": "TERMINATED", "t": "TERMINATED", "leaver": "TERMINATED",
        "inactive": "TERMINATED", "separated": "TERMINATED", "exited": "TERMINATED", "dismissed": "TERMINATED",
        "resigned": "RESIGNED", "resignation": "RESIGNED",
        "suspended": "SUSPENDED", "s": "SUSPENDED",
    },
    "pay_status": {
        "active": "ACTIVE", "a": "ACTIVE", "paid": "ACTIVE", "live": "ACTIVE", "1": "ACTIVE", "y": "ACTIVE", "yes": "ACTIVE", "true": "ACTIVE",
        "inactive": "INACTIVE", "i": "INACTIVE", "stopped": "INACTIVE", "terminated": "INACTIVE", "closed": "INACTIVE",
        "0": "INACTIVE", "n": "INACTIVE", "no": "INACTIVE", "false": "INACTIVE",
        "hold": "HOLD", "onhold": "HOLD", "suspended": "HOLD", "h": "HOLD",
    },
    "account_status": {
        "active": "Active", "enabled": "Active", "1": "Active", "true": "Active", "y": "Active", "yes": "Active",
        "disabled": "Disabled", "inactive": "Disabled", "0": "Disabled", "false": "Disabled", "n": "Disabled",
        "no": "Disabled", "locked": "Disabled", "deleted": "Disabled",
    },
}

_DATE_FORMATS = (
    "%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d-%b-%Y", "%d %b %Y",
    "%d-%B-%Y", "%d %B %Y", "%b %d, %Y", "%Y%m%d",
    "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ", "%d/%m/%Y %H:%M",
)

def parse_any_date(value: Optional[str]) -> Optional[datetime]:
    """Parses a date in any common HR export format (day-first for ambiguous slashes)."""
    if not value:
        return None
    v = str(value).strip()
    if not v or v.upper() in ("N/A", "NA", "NULL", "NONE", "-"):
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(v, fmt)
        except ValueError:
            pass
    # Fallback: ISO with fractional seconds / timezone
    try:
        return datetime.fromisoformat(v.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None

def normalize_id(value: Optional[str]) -> str:
    """Upper-cases and strips separators/whitespace from an identifier."""
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())

class SchemaMapper:
    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        self.overrides: Dict[str, Any] = {}
        override_path = os.path.join(data_dir, "schema_mapping.json")
        if os.path.exists(override_path):
            with open(override_path, "r", encoding="utf-8") as f:
                self.overrides = json.load(f)
        self.report: Dict[str, Any] = {}
        self._claimed: set = set()

    # ---------- file discovery ----------
    def find_file(self, system: str) -> Optional[str]:
        pinned = self.overrides.get(system, {}).get("file")
        if pinned:
            self._claimed.add(pinned)
            return os.path.join(self.data_dir, pinned)
        files = [f for f in os.listdir(self.data_dir)
                 if f.lower().endswith((".csv", ".xlsx", ".xls", ".json")) and f not in self._claimed
                 and f != "schema_mapping.json"]
        exact = f"{system}.csv"
        if exact in files:
            self._claimed.add(exact)
            return os.path.join(self.data_dir, exact)
        for hint in FILE_HINTS[system]:
            for f in sorted(files):
                if hint in f.lower().replace("-", "_").replace(" ", "_"):
                    self._claimed.add(f)
                    return os.path.join(self.data_dir, f)
        return None

    # ---------- column mapping ----------
    def map_columns(self, system: str, headers: List[str], rows: List[Dict[str, Any]]) -> Dict[str, str]:
        """Returns canonical_field -> source_header."""
        schema = CANONICAL_SCHEMAS[system]
        pinned: Dict[str, str] = self.overrides.get(system, {}).get("columns", {})
        mapping: Dict[str, str] = {}
        how: Dict[str, str] = {}
        used = set()

        for canon, src in pinned.items():
            if src in headers:
                mapping[canon] = src
                how[canon] = "override"
                used.add(src)

        by_norm = {norm_header(h): h for h in headers}
        # Exact canonical names first, then aliases in priority order
        for canon, aliases in schema.items():
            if canon in mapping:
                continue
            for alias in [canon] + aliases:
                h = by_norm.get(norm_header(alias))
                if h and h not in used:
                    mapping[canon] = h
                    how[canon] = "exact" if norm_header(alias) == norm_header(canon) else f"alias:{alias}"
                    used.add(h)
                    break

        # Keyword fallback on remaining headers
        for canon in schema:
            if canon in mapping:
                continue
            for h in headers:
                nh = norm_header(h)
                if h not in used and any(t in nh for t in TOKEN_HINTS.get(canon, [])):
                    mapping[canon] = h
                    how[canon] = "header-keyword"
                    used.add(h)
                    break

        # Content sniffing for anything still missing
        sample = rows[:200]
        for canon, sniff in _SNIFFERS.items():
            if canon not in schema or canon in mapping:
                continue
            for h in headers:
                if h in used:
                    continue
                vals = [str(r.get(h) or "").strip() for r in sample]
                vals = [v for v in vals if v]
                if vals and sum(sniff(v) for v in vals) / len(vals) >= 0.8:
                    mapping[canon] = h
                    how[canon] = "content-sniffed"
                    used.add(h)
                    break

        self.report[system] = {
            "mapped": {c: {"source_column": mapping[c], "method": how[c]} for c in mapping},
            "missing_canonical_fields": [c for c in schema if c not in mapping],
            "unmapped_source_columns": [h for h in headers if h not in used],
        }
        return mapping

    # ---------- reference-key sniffing ----------
    REF_FIELDS = {"payroll": "employee_ref", "learning": "emp_core_id", "access_directory": "employee_number"}

    def sniff_reference_column(self, system: str, raw_rows: List[Dict[str, Any]], core_ids: List[str]) -> Optional[str]:
        """If the employee-reference header was not recognized, pick the column whose values overlap Core HR IDs most."""
        ref = self.REF_FIELDS.get(system)
        rep = self.report.get(system, {})
        if not ref or ref in rep.get("mapped", {}) or not raw_rows:
            return None
        norm_ids = {normalize_id(c) for c in core_ids}
        digit_ids = {re.sub(r"\D", "", c).lstrip("0") for c in core_ids}
        used = {m["source_column"] for m in rep.get("mapped", {}).values()}
        sample = raw_rows[:500]
        best, best_rate = None, 0.0
        for h in raw_rows[0].keys():
            vals = [str(r.get(h) or "").strip() for r in sample]
            vals = [v for v in vals if v]
            if not vals:
                continue
            hits = sum(1 for v in vals if normalize_id(v) in norm_ids or re.sub(r"\D", "", v).lstrip("0") in digit_ids)
            rate = hits / len(vals)
            if rate > best_rate and (h not in used or rate > 0.9):
                best, best_rate = h, rate
        if best and best_rate >= 0.6:
            self.overrides.setdefault(system, {}).setdefault("columns", {})[ref] = best
            return best
        return None

    # ---------- row normalization ----------
    def canonicalize(self, system: str, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not rows:
            self.report[system] = {"mapped": {}, "missing_canonical_fields": list(CANONICAL_SCHEMAS[system]), "unmapped_source_columns": []}
            return []
        headers = list(rows[0].keys())
        mapping = self.map_columns(system, headers, rows)
        out = []
        for r in rows:
            rec = {canon: (str(r.get(src)).strip() if r.get(src) is not None else "") for canon, src in mapping.items()}
            self._normalize_values(system, rec)
            # Keep unmapped source columns for evidence/explainability
            rec["_source_extra"] = {h: r.get(h) for h in headers if h not in mapping.values()}
            out.append(rec)
        return out

    def _normalize_values(self, system: str, rec: Dict[str, Any]):
        # Split / build names
        if system == "core_hr":
            if not rec.get("first_name") and not rec.get("last_name") and rec.get("full_name"):
                fn = rec["full_name"]
                if "," in fn:
                    last, first = [p.strip() for p in fn.split(",", 1)]
                else:
                    parts = fn.split()
                    first, last = (parts[0], " ".join(parts[1:])) if parts else ("", "")
                rec["first_name"], rec["last_name"] = first, last
            for k in ("department_code", "job_grade", "work_location", "nationality"):
                if rec.get(k):
                    rec[k] = rec[k].strip().upper()

        # Status vocabularies
        for field, vocab in STATUS_MAPS.items():
            if field in rec and rec[field]:
                key = norm_header(rec[field])
                rec[field] = vocab.get(key, rec[field].strip().upper() if field != "account_status" else rec[field].strip())

        # Dates -> ISO for core_hr (system of record); other systems keep a parsed ISO shadow
        for f in DATE_FIELDS.get(system, []):
            raw = rec.get(f)
            if not raw:
                continue
            d = parse_any_date(raw)
            if system == "core_hr":
                rec[f] = d.strftime("%Y-%m-%d") if d else raw
            else:
                rec[f + "_iso"] = d.strftime("%Y-%m-%d") if d else ""

        # Salary: strip currency text / thousands separators
        if system == "payroll" and rec.get("monthly_basic_aed"):
            num = re.sub(r"[^0-9.\-]", "", rec["monthly_basic_aed"])
            rec["monthly_basic_aed"] = num or rec["monthly_basic_aed"]
        if system == "payroll" and rec.get("bank_iban"):
            rec["bank_iban"] = rec["bank_iban"].replace(" ", "").upper()
