"""
Multi-source ingestion and reference catalog parser for VeritasHR.
Loads raw system CSV files and extracts controlled vocabularies and lineage graphs from markdown definitions.
"""

import os
import re
import csv
import io
import json
from typing import Dict, List, Any, Set, Tuple
from src.ingestion.schema_mapper import SchemaMapper

class ReferenceCatalog:
    def __init__(self):
        self.departments: Set[str] = set()
        self.job_grades: Set[str] = set()
        self.locations: Set[str] = set()
        self.statuses: Dict[str, Set[str]] = {
            "core_hr": {"ACTIVE", "ON_LEAVE", "TERMINATED", "RESIGNED", "SUSPENDED"},
            "payroll": {"ACTIVE", "INACTIVE", "HOLD"},
            "access_directory": {"Active", "Disabled"}
        }
        self.code_descriptions: Dict[str, str] = {}
        self.report_dependencies: Dict[str, Dict[str, Any]] = {}
        self.system_lineage: List[Tuple[str, str, str]] = []

def parse_data_dictionary(file_path: str) -> ReferenceCatalog:
    """Parses data_dictionary.md to extract valid controlled vocabularies."""
    catalog = ReferenceCatalog()
    if not os.path.exists(file_path):
        # Fallback default Emirates standards
        catalog.departments = {
            "EK-FLIGHT-OPS", "EK-CABIN-CREW", "EK-ENG", "EK-AIRPORT-SVCS",
            "EK-COMMERCIAL", "EK-IT", "EK-HR", "DNATA-GROUND-SVCS",
            "DNATA-CARGO", "DNATA-TRAVEL"
        }
        catalog.locations = {"DXB-HQ", "DXB-T3", "DWC-ALMAKTOUM", "AUH-HUB", "LHR-STATION", "JFK-STATION", "SIN-STATION"}
        catalog.job_grades = {f"G{i:02d}" for i in range(1, 13)} | {f"CR{i:02d}" for i in range(1, 7)} | {f"T{i:02d}" for i in range(1, 9)} | {f"E{i:02d}" for i in range(1, 6)}
        return catalog

    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Generic section parse: "### Title (`field`)" followed by `CODE`: description lines
    for m in re.finditer(r"^###\s+(.+?)\n(.*?)(?=^#{2,3}\s|\Z)", content, re.DOTALL | re.MULTILINE):
        title, body = m.group(1).lower(), m.group(2)
        codes = re.findall(r"`([A-Za-z0-9_\-]+)`\s*:", body)
        for code, desc in re.findall(r"`([A-Za-z0-9_\-]+)`\s*:\s*(.+)", body):
            catalog.code_descriptions[code.upper()] = desc.strip()
        # Ranges such as `G01` to `G12`
        range_codes = set()
        for a, b in re.findall(r"`([A-Z]+\d+)`\s*(?:to|-|–)\s*`([A-Z]+\d+)`", body):
            pa, na = re.match(r"([A-Z]+)(\d+)", a).groups()
            pb, nb = re.match(r"([A-Z]+)(\d+)", b).groups()
            if pa == pb:
                width = len(na)
                range_codes.update(f"{pa}{i:0{width}d}" for i in range(int(na), int(nb) + 1))
        if "department" in title or "org" in title or "cost cent" in title:
            catalog.departments.update(c.upper() for c in codes)
        elif "location" in title or "station" in title:
            catalog.locations.update(c.upper() for c in codes)
        elif "grade" in title:
            catalog.job_grades.update(range_codes | {c.upper() for c in codes})
        elif "status" in title:
            for line in body.splitlines():
                lm = re.match(r"\s*[-*]\s*(.+?):\s*(.+)", line)
                if not lm:
                    continue
                sysname = lm.group(1).lower()
                vals = set(re.findall(r"`([A-Za-z_]+)`", lm.group(2)))
                if "core" in sysname or sysname == "hr":
                    key = "core_hr"
                elif "pay" in sysname:
                    key = "payroll"
                elif "access" in sysname or "directory" in sysname:
                    key = "access_directory"
                else:
                    key = None
                if key and vals:
                    catalog.statuses[key] = vals

    if not catalog.job_grades:
        catalog.job_grades = {f"G{i:02d}" for i in range(1, 13)} | {f"CR{i:02d}" for i in range(1, 7)} | {f"T{i:02d}" for i in range(1, 9)} | {f"E{i:02d}" for i in range(1, 6)}

    if not catalog.departments:
        catalog.departments = {
            "EK-FLIGHT-OPS", "EK-CABIN-CREW", "EK-ENG", "EK-AIRPORT-SVCS",
            "EK-COMMERCIAL", "EK-IT", "EK-HR", "DNATA-GROUND-SVCS",
            "DNATA-CARGO", "DNATA-TRAVEL"
        }
    if not catalog.locations:
        catalog.locations = {"DXB-HQ", "DXB-T3", "DWC-ALMAKTOUM", "AUH-HUB", "LHR-STATION", "JFK-STATION", "SIN-STATION"}

    return catalog

def parse_dependencies(file_path: str) -> Dict[str, Any]:
    """Parses dependencies.md into a structured lineage and report dependency map."""
    reports = {
        "REP-EXEC-HEADCOUNT": {
            "name": "Executive Headcount & Emaratisation Dashboard",
            "owner": "CHRO & Executive Board",
            "fields": ["core_hr.employment_status", "core_hr.department_code", "core_hr.nationality", "core_hr.work_location", "core_hr.job_grade"],
            "impact": "Workforce sizing distortions & UAE Emiratisation statutory quota breaches."
        },
        "REP-WPS-PAYROLL": {
            "name": "Monthly Wages Protection System (WPS) File",
            "owner": "MOHRE & UAE Central Bank",
            "fields": ["payroll.payroll_id", "payroll.bank_iban", "payroll.monthly_basic_aed", "payroll.pay_status", "core_hr.national_id", "core_hr.employment_status"],
            "impact": "WPS transaction rejection, cash leakage to terminated staff, regulatory labor fines."
        },
        "REP-GCAA-SAFETY": {
            "name": "GCAA Aviation Safety Compliance & Airworthiness Audit",
            "owner": "UAE GCAA & IATA",
            "fields": ["core_hr.job_title", "core_hr.department_code", "learning.aviation_safety_cert", "learning.compliance_status"],
            "impact": "Aircraft groundings, pilot flight duty non-compliance, regulatory safety citations."
        },
        "REP-SEC-OFFBOARDING": {
            "name": "IT Security & Identity Offboarding Audit",
            "owner": "Group CISO & Internal Audit",
            "fields": ["core_hr.termination_date", "core_hr.employment_status", "access_directory.account_status", "access_directory.last_logon_timestamp"],
            "impact": "Critical cyber risk: unauthorized active logins by terminated employees, ISO 27001 violation."
        },
        "REP-LMS-BUDGET": {
            "name": "Group Learning & Development Budget Allocation",
            "owner": "VP Talent & Development",
            "fields": ["learning.assigned_department", "core_hr.job_grade", "payroll.cost_center"],
            "impact": "Departmental mischarges and unallocated training overhead."
        }
    }
    
    feeds = [
        ("core_hr", "payroll", "Employee Onboarding, Grade & Termination Sync"),
        ("core_hr", "access_directory", "IAM Account Provisioning & Deprovisioning"),
        ("core_hr", "learning", "LMS User Role & Mandatory Training Assignment"),
        ("payroll", "REP-WPS-PAYROLL", "Monthly Disbursement & IBAN Feed"),
        ("learning", "REP-GCAA-SAFETY", "Flight Crew Airworthiness Certification Feed"),
        ("access_directory", "REP-SEC-OFFBOARDING", "Security Audit & Account State Feed"),
        ("core_hr", "REP-EXEC-HEADCOUNT", "Headcount & Demographics Feed")
    ]
    
    parsed = _parse_dependencies_md(file_path)
    if parsed["reports"]:
        # The published lineage file is authoritative; built-in entries only fill gaps
        for rid, meta in parsed["reports"].items():
            reports[rid] = {**reports.get(rid, {}), **{k: v for k, v in meta.items() if v}}
    if parsed["feeds"]:
        feeds = parsed["feeds"]
    return {"reports": reports, "feeds": feeds, "source": "dependencies.md" if parsed["reports"] else "built-in defaults"}

_SYSTEM_KEYWORDS = [
    ("payroll", "payroll"), ("wps", "WPS"), ("lms", "learning"), ("learning", "learning"),
    ("access", "access_directory"), ("directory", "access_directory"), ("iam", "access_directory"),
    ("core", "core_hr"), ("hris", "core_hr"), ("gcaa", "GCAA"),
]

def _node_to_system(node_id: str, label: str) -> str:
    """Maps a mermaid node (e.g. PAYROLL[Payroll System], REP1[REP-EXEC-HEADCOUNT]) to a system or report id."""
    rep = re.search(r"(REP-[A-Z0-9\-]+)", label or "")
    if rep:
        return rep.group(1)
    text = f"{node_id} {label}".lower()
    if re.search(r"\bad\b", text):
        return "access_directory"
    for kw, system in _SYSTEM_KEYWORDS:
        if kw in text:
            return system
    return (label or node_id).strip()

def _parse_dependencies_md(file_path: str) -> Dict[str, Any]:
    """Reads report field dependencies and system feeds from dependencies.md (mermaid graph + report sections)."""
    out: Dict[str, Any] = {"reports": {}, "feeds": []}
    if not os.path.exists(file_path):
        return out
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Reports: "### REP-ID: Name" followed by bullet metadata and `system.field` critical fields
    for m in re.finditer(r"^###\s+(REP-[A-Z0-9\-]+)\s*:\s*(.+?)\n(.*?)(?=^#{2,3}\s|\Z)", content, re.DOTALL | re.MULTILINE):
        rid, name, body = m.group(1), m.group(2).strip(), m.group(3)
        owner = re.search(r"\*\*(?:Executive Owner|Regulatory Authority|Owner)\*\*\s*:\s*(.+)", body)
        impact = re.search(r"\*\*(?:Downstream Impact|Impact)\*\*\s*:\s*(.+)", body)
        fields = re.findall(r"`([a-z_]+\.[a-z_0-9]+)`", body)
        out["reports"][rid] = {
            "name": name,
            "owner": owner.group(1).strip() if owner else "",
            "fields": fields,
            "impact": impact.group(1).strip() if impact else "",
            "regulatory": bool(re.search(r"Regulatory|MOHRE|GCAA|Central Bank|ISO", body)),
        }

    # Feeds: mermaid edges  A[Label] -->|edge label| B[Label]
    labels = dict(re.findall(r"([A-Za-z0-9_]+)\[([^\]]+)\]", content))
    for a, lab, b in re.findall(r"([A-Za-z0-9_]+)(?:\[[^\]]*\])?\s*-->\s*(?:\|([^|]*)\|)?\s*([A-Za-z0-9_]+)", content):
        src, dst = _node_to_system(a, labels.get(a, a)), _node_to_system(b, labels.get(b, b))
        if src != dst:
            out["feeds"].append((src, dst, (lab or "").strip()))
    return out

class DataLoader:
    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        self.catalog = parse_data_dictionary(os.path.join(data_dir, "data_dictionary.md"))
        self.dependencies = parse_dependencies(os.path.join(data_dir, "dependencies.md"))
        self.mapper = SchemaMapper(data_dir)
        
    def read_table(self, path: str) -> List[Dict[str, Any]]:
        """Reads CSV (any delimiter/encoding), Excel or JSON into a list of dicts."""
        ext = os.path.splitext(path)[1].lower()
        if ext in (".xlsx", ".xls"):
            import pandas as pd
            return pd.read_excel(path, dtype=str).fillna("").to_dict("records")
        if ext == ".json":
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, list) else data.get("records", [])
        for enc in ("utf-8-sig", "cp1252", "latin-1"):
            try:
                with open(path, "r", encoding=enc, newline="") as f:
                    text = f.read()
                break
            except UnicodeDecodeError:
                continue
        try:
            dialect = csv.Sniffer().sniff(text[:5000], delimiters=",;|	")
        except csv.Error:
            dialect = csv.excel
        return list(csv.DictReader(io.StringIO(text), dialect=dialect))

    def load_csv(self, filename: str) -> List[Dict[str, Any]]:
        path = os.path.join(self.data_dir, filename)
        if not os.path.exists(path):
            raise FileNotFoundError(f"Required dataset file not found: {path}")
        return self.read_table(path)

    def load_all_sources(self) -> Dict[str, List[Dict[str, Any]]]:
        """Discovers, loads and canonicalizes all four system extracts, whatever their layout."""
        sources = {}
        for system in ("core_hr", "payroll", "learning", "access_directory"):
            path = self.mapper.find_file(system)
            if not path or not os.path.exists(path):
                raise FileNotFoundError(f"No source file found for system '{system}' in {self.data_dir}")
            raw = self.read_table(path)
            sources[system] = self.mapper.canonicalize(system, raw)
            if system != "core_hr":
                core_ids = [r.get("employee_id", "") for r in sources["core_hr"]]
                if self.mapper.sniff_reference_column(system, raw, core_ids):
                    sources[system] = self.mapper.canonicalize(system, raw)
                    self.mapper.report[system]["mapped"][self.mapper.REF_FIELDS[system]]["method"] = "content-sniffed:id-overlap"
            self.mapper.report[system]["file"] = os.path.basename(path)
        self.extra_sources = self._load_extra_sources(sources["core_hr"])
        return sources

    def _load_extra_sources(self, core_rows) -> Dict[str, List[Dict[str, Any]]]:
        """Any other table in the folder with an employee reference column is onboarded as an extra system."""
        from src.anomaly.extra_sources import register_extra_schema, system_name
        extras: Dict[str, List[Dict[str, Any]]] = {}
        core_ids = [r.get("employee_id", "") for r in core_rows]
        for f in sorted(os.listdir(self.data_dir)):
            if f in self.mapper._claimed or f == "schema_mapping.json" or not f.lower().endswith((".csv", ".xlsx", ".xls", ".json"))                     or any(k in f.lower() for k in ("answer_key", "ground_truth")):
                continue
            try:
                raw = self.read_table(os.path.join(self.data_dir, f))
            except Exception as e:
                self.mapper.report[f] = {"file": f, "skipped": f"could not read ({e})", "mapped": {}, "missing_canonical_fields": [], "unmapped_source_columns": []}
                continue
            if not raw or not isinstance(raw[0], dict):
                continue
            system = system_name(f)
            register_extra_schema(system)
            self.mapper.REF_FIELDS[system] = "employee_ref"
            rows = self.mapper.canonicalize(system, raw)
            if "employee_ref" not in self.mapper.report[system]["mapped"] and self.mapper.sniff_reference_column(system, raw, core_ids):
                rows = self.mapper.canonicalize(system, raw)
            self.mapper.report[system]["file"] = f
            if "employee_ref" not in self.mapper.report[system]["mapped"]:
                self.mapper.report[system]["skipped"] = "no employee ID column found"
                continue
            extras[system] = rows
        return extras
