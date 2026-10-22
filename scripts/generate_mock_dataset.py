"""
Synthetic HR Dataset Generator for Emirates Group HR Data Quality Challenge.
Generates:
  - data/raw/core_hr.csv
  - data/raw/payroll.csv
  - data/raw/learning.csv
  - data/raw/access_directory.csv
  - data/raw/data_dictionary.md
  - data/raw/dependencies.md
  - data/ground_truth_errors.json (Answer key for benchmarking)
"""

import os
import csv
import json
import random
from datetime import datetime, timedelta

random.seed(42)

RAW_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "raw")
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
os.makedirs(RAW_DIR, exist_ok=True)

NUM_EMPLOYEES = 5000

# Controlled Reference Vocabularies
DEPARTMENTS = [
    "EK-FLIGHT-OPS",      # Flight Operations (Pilots)
    "EK-CABIN-CREW",      # Cabin Crew Services
    "EK-ENG",             # Engineering & Fleet Maintenance
    "EK-AIRPORT-SVCS",    # Airport Passenger Services
    "EK-COMMERCIAL",      # Global Sales & Revenue Management
    "EK-IT",              # Group IT & Digital
    "EK-HR",              # Group Human Resources
    "DNATA-GROUND-SVCS",  # Dnata Ground Handling & Ramp
    "DNATA-CARGO",        # Dnata Freight & Logistics
    "DNATA-TRAVEL",       # Dnata Retail & Corporate Travel
]

JOB_TITLES = {
    "EK-FLIGHT-OPS": [("A380 Captain", "CR05"), ("B777 First Officer", "CR03"), ("Fleet Training Captain", "CR06")],
    "EK-CABIN-CREW": [("Cabin Senior", "CR02"), ("Flight Attendant", "CR01"), ("Purser", "CR03")],
    "EK-ENG": [("Avionics Specialist", "T04"), ("Licensed Aircraft Engineer", "T05"), ("Maintenance Planner", "G06")],
    "EK-AIRPORT-SVCS": [("Check-in Agent", "G03"), ("Boarding Supervisor", "G05"), ("Duty Station Manager", "G08")],
    "EK-COMMERCIAL": [("Revenue Analyst", "G06"), ("Key Account Executive", "G07"), ("Pricing Manager", "E01")],
    "EK-IT": [("Senior Data Engineer", "G08"), ("Cloud Architect", "G09"), ("Cybersecurity Specialist", "G07")],
    "EK-HR": [("HR Business Partner", "G07"), ("Talent Acquisition Specialist", "G05"), ("Reward Lead", "G08")],
    "DNATA-GROUND-SVCS": [("Ramp Controller", "G04"), ("Baggage Operations Lead", "G05"), ("Airside Safety Officer", "G06")],
    "DNATA-CARGO": [("Cargo Acceptance Agent", "G03"), ("Dangerous Goods Specialist", "G05"), ("Cargo Hub Manager", "G08")],
    "DNATA-TRAVEL": [("Travel Consultant", "G03"), ("Corporate Account Manager", "G06"), ("Operations Lead", "G07")]
}

LOCATIONS = ["DXB-HQ", "DXB-T3", "DWC-ALMAKTOUM", "AUH-HUB", "LHR-STATION", "JFK-STATION", "SIN-STATION"]
NATIONALITIES = ["AE", "GB", "IN", "AU", "ZA", "EG", "PH", "PK", "FR", "US", "LB", "JO", "DE"]

FIRST_NAMES_M = ["Ahmed", "Mohammed", "Saeed", "Rashid", "Omar", "John", "David", "James", "Rahul", "Ali", "Jean", "Carlos", "Tariq", "Hassan", "Michael"]
FIRST_NAMES_F = ["Fatima", "Maryam", "Ayesha", "Sarah", "Emily", "Priya", "Noor", "Layla", "Elena", "Chloe", "Hana", "Zainab", "Jessica", "Amira", "Sophie"]
LAST_NAMES = ["Al Mansoori", "Al Marzooqi", "Al Falasi", "Smith", "Johnson", "Sharma", "Khan", "Patel", "Dubois", "Williams", "Al Hashimi", "Al Suwaidi", "Taylor", "Brown", "Al Zaabi"]

UAE_BANKS = ["ENBD", "ADCB", "DIB", "FAB", "CBD", "RAKBANK"]

def generate_iban(bank_code, account_num):
    # Standard UAE IBAN format: AE + 2 check digits + 3 bank char code + 16 numeric digits = 23 chars
    return f"AE{random.randint(10,99)}{bank_code}{account_num:016d}"

def random_date(start_year=2010, end_year=2024):
    start = datetime(start_year, 1, 1)
    end = datetime(end_year, 12, 31)
    delta = end - start
    return start + timedelta(days=random.randint(0, delta.days))

def format_date_iso(dt):
    return dt.strftime("%Y-%m-%d") if dt else ""

def format_date_payroll(dt):
    return dt.strftime("%d/%m/%Y") if dt else ""

print("Generating synthetic HR ecosystem records...")

core_records = []
payroll_records = []
learning_records = []
directory_records = []

# Ground truth tracking
planted_errors = []

for i in range(1, NUM_EMPLOYEES + 1):
    ek_id = f"EK{10000 + i}"
    gender = random.choice(["M", "F"])
    first_name = random.choice(FIRST_NAMES_M if gender == "M" else FIRST_NAMES_F)
    last_name = random.choice(LAST_NAMES)
    nationality = random.choice(NATIONALITIES)
    dept = random.choice(DEPARTMENTS)
    job_title, grade = random.choice(JOB_TITLES[dept])
    loc = "DXB-HQ" if dept in ["EK-HR", "EK-IT"] else random.choice(LOCATIONS)
    
    dob = random_date(1965, 2002)
    hire_date = random_date(2012, 2023)
    is_terminated = random.random() < 0.08  # 8% attrition rate
    term_date = hire_date + timedelta(days=random.randint(90, 1500)) if is_terminated else None
    status = "TERMINATED" if is_terminated else "ACTIVE"
    
    national_id = f"784-{dob.year}-{random.randint(1000000, 9999999)}-{random.randint(1,9)}"
    passport_num = f"P{random.randint(10000000, 99999999)}"
    
    # Base salary in AED by grade tier
    if grade.startswith("E"):
        base_salary = random.randint(45000, 85000)
    elif grade.startswith("CR05") or grade.startswith("CR06"):
        base_salary = random.randint(40000, 65000)
    elif grade.startswith("CR") or grade.startswith("T"):
        base_salary = random.randint(18000, 38000)
    else:
        num = int(grade[1:]) if grade[1:].isdigit() else 5
        base_salary = 8000 + (num * 2500)
        
    bank = random.choice(UAE_BANKS)
    iban = generate_iban(bank[:3], i * 987)

    # Core HR
    core_records.append({
        "employee_id": ek_id,
        "first_name": first_name,
        "last_name": last_name,
        "date_of_birth": format_date_iso(dob),
        "gender": gender,
        "nationality": nationality,
        "national_id": national_id,
        "passport_number": passport_num,
        "department_code": dept,
        "job_title": job_title,
        "job_grade": grade,
        "work_location": loc,
        "employment_status": status,
        "hire_date": format_date_iso(hire_date),
        "termination_date": format_date_iso(term_date) if term_date else ""
    })
    
    # Payroll (different ID, different name format, DD/MM/YYYY dates)
    pr_id = f"PR-{90000 + i}"
    pr_status = "INACTIVE" if is_terminated else "ACTIVE"
    pr_name = f"{last_name.upper()}, {first_name.upper()}"
    payroll_records.append({
        "payroll_id": pr_id,
        "employee_ref": ek_id,
        "legal_name": pr_name,
        "bank_iban": iban,
        "bank_name": bank,
        "monthly_basic_aed": base_salary,
        "currency": "AED",
        "cost_center": f"CC-{dept}",
        "pay_status": pr_status,
        "effective_start_date": format_date_payroll(hire_date)
    })
    
    # Learning LMS
    lms_id = f"LMS-{40000 + i}"
    cert_status = "COMPLIANT" if not is_terminated else "EXPIRED"
    learning_records.append({
        "lms_user_id": lms_id,
        "emp_core_id": ek_id,
        "full_name": f"{first_name} {last_name}",
        "assigned_department": dept,
        "job_role": job_title,
        "aviation_safety_cert": "VALID" if dept in ["EK-FLIGHT-OPS", "EK-CABIN-CREW", "EK-ENG"] else "N/A",
        "last_training_date": format_date_iso(hire_date + timedelta(days=60)),
        "compliance_status": cert_status
    })
    
    # Access Directory (Active Directory / IAM)
    ad_username = f"{first_name.lower()}.{last_name.lower().replace(' ', '')}{'' if i < 3000 else str(i%100)}"
    ad_email = f"{ad_username}@emirates.group"
    ad_status = "Disabled" if is_terminated else "Active"
    last_login = datetime(2024, 10, random.randint(1, 15), random.randint(8, 18), random.randint(0, 59)) if not is_terminated else datetime(2023, 5, 10)
    directory_records.append({
        "samaccountname": ad_username,
        "work_email": ad_email,
        "employee_number": ek_id,
        "display_name": f"{first_name} {last_name} ({dept})",
        "account_status": ad_status,
        "badge_id": f"BDG-{70000 + i}",
        "last_logon_timestamp": last_login.strftime("%Y-%m-%d %H:%M:%S")
    })

print("Planting controlled errors across categories...")

# -------------------------------------------------------------
# Category 1: GHOST PAYROLL (Financial Impact: High / Critical)
# Terminated in Core HR, but still ACTIVE on Payroll receiving salary!
# -------------------------------------------------------------
ghost_count = 35
terminated_indices = [idx for idx, r in enumerate(core_records) if r["employment_status"] == "TERMINATED"]
selected_ghosts = random.sample(terminated_indices, ghost_count)

for idx in selected_ghosts:
    emp = core_records[idx]
    pay = payroll_records[idx]
    pay["pay_status"] = "ACTIVE"  # Planted error!
    planted_errors.append({
        "issue_id": f"ERR-GHOST-{emp['employee_id']}",
        "category": "GHOST_RECORD",
        "severity": "CRITICAL",
        "primary_entity_id": emp["employee_id"],
        "entity_name": f"{emp['first_name']} {emp['last_name']}",
        "source_systems": ["core_hr", "payroll"],
        "description": f"Employee {emp['employee_id']} was TERMINATED in Core HR on {emp['termination_date']} but remains ACTIVE in Payroll system receiving monthly salary of AED {pay['monthly_basic_aed']:,}.",
        "field_in_conflict": "employment_status vs pay_status",
        "current_values": {"core_hr.employment_status": "TERMINATED", "payroll.pay_status": "ACTIVE"},
        "suggested_fix": "Set payroll.pay_status to 'INACTIVE' and initiate payroll clawback audit.",
        "affected_reports": ["REP-WPS-PAYROLL", "REP-EXEC-HEADCOUNT"],
        "business_risk": f"Direct unauthorized cash leakage (~AED {pay['monthly_basic_aed']*3:,} over 3 months) and WPS non-compliance fines."
    })

# -------------------------------------------------------------
# Category 2: ZOMBIE ACCESS ACCOUNTS (Security & Audit: High / Critical)
# Terminated in Core HR, but still Active in Active Directory with recent logins!
# -------------------------------------------------------------
zombie_count = 35
active_term_indices = [idx for idx in terminated_indices if idx not in selected_ghosts]
selected_zombies = random.sample(active_term_indices, zombie_count)

for idx in selected_zombies:
    emp = core_records[idx]
    ad = directory_records[idx]
    ad["account_status"] = "Active"
    ad["last_logon_timestamp"] = "2024-10-12 14:32:10"  # Active login after termination!
    planted_errors.append({
        "issue_id": f"ERR-ZOMBIE-{emp['employee_id']}",
        "category": "SECURITY_EXPOSURE",
        "severity": "HIGH",
        "primary_entity_id": emp["employee_id"],
        "entity_name": f"{emp['first_name']} {emp['last_name']}",
        "source_systems": ["core_hr", "access_directory"],
        "description": f"Terminated employee {emp['employee_id']} (exited {emp['termination_date']}) still has an 'Active' Active Directory account with recent login on 2024-10-12.",
        "field_in_conflict": "employment_status vs account_status",
        "current_values": {"core_hr.employment_status": "TERMINATED", "access_directory.account_status": "Active", "access_directory.last_logon": "2024-10-12 14:32:10"},
        "suggested_fix": "Immediately disable AD account and revoke badge access BDG.",
        "affected_reports": ["REP-SEC-OFFBOARDING"],
        "business_risk": "Severe IT security vulnerability, unauthorized access to corporate network, ISO 27001 audit non-compliance."
    })

# -------------------------------------------------------------
# Category 3: DEPARTMENT & COST CENTER CONFLICTS (Operational / Budget: Medium)
# Core HR updated department, but Payroll or LMS still in legacy dept.
# -------------------------------------------------------------
dept_conflict_count = 50
active_indices = [idx for idx, r in enumerate(core_records) if r["employment_status"] == "ACTIVE"]
selected_dept_conflicts = random.sample(active_indices, dept_conflict_count)

for idx in selected_dept_conflicts:
    emp = core_records[idx]
    pay = payroll_records[idx]
    old_dept = random.choice([d for d in DEPARTMENTS if d != emp["department_code"]])
    pay["cost_center"] = f"CC-{old_dept}"
    planted_errors.append({
        "issue_id": f"ERR-DEPT-{emp['employee_id']}",
        "category": "DEPARTMENT_CONFLICT",
        "severity": "MEDIUM",
        "primary_entity_id": emp["employee_id"],
        "entity_name": f"{emp['first_name']} {emp['last_name']}",
        "source_systems": ["core_hr", "payroll"],
        "description": f"Department mismatch: Core HR assigns employee to '{emp['department_code']}', but Payroll is billing cost center 'CC-{old_dept}'.",
        "field_in_conflict": "department_code vs cost_center",
        "current_values": {"core_hr.department_code": emp["department_code"], "payroll.cost_center": f"CC-{old_dept}"},
        "suggested_fix": f"Update payroll.cost_center to 'CC-{emp['department_code']}'.",
        "affected_reports": ["REP-EXEC-HEADCOUNT", "REP-LMS-BUDGET"],
        "business_risk": "Cost center cross-charging errors and skewed departmental budget reporting."
    })

# -------------------------------------------------------------
# Category 4: INVALID REFERENCE CODES (Data Integrity: Medium)
# Invalid department code, non-standard grades or locations.
# -------------------------------------------------------------
invalid_codes_count = 45
selected_invalid_codes = random.sample(active_indices[:1500], invalid_codes_count)
for i, idx in enumerate(selected_invalid_codes):
    emp = core_records[idx]
    if i % 3 == 0:
        emp["department_code"] = "EK-FLT-OPS"  # Typo for EK-FLIGHT-OPS
        field = "department_code"
        bad_val = "EK-FLT-OPS"
        sugg = "EK-FLIGHT-OPS"
    elif i % 3 == 1:
        emp["job_grade"] = "G99"  # Invalid grade
        field = "job_grade"
        bad_val = "G99"
        sugg = "G07"
    else:
        emp["work_location"] = "DXB-AIR"  # Invalid location code
        field = "work_location"
        bad_val = "DXB-AIR"
        sugg = "DXB-T3"
        
    planted_errors.append({
        "issue_id": f"ERR-CODE-{emp['employee_id']}",
        "category": "INVALID_CODE",
        "severity": "MEDIUM",
        "primary_entity_id": emp["employee_id"],
        "entity_name": f"{emp['first_name']} {emp['last_name']}",
        "source_systems": ["core_hr"],
        "description": f"Field '{field}' contains invalid value '{bad_val}' not listed in standard Emirates Group data dictionary.",
        "field_in_conflict": field,
        "current_values": {f"core_hr.{field}": bad_val},
        "suggested_fix": f"Correct {field} to valid standardized code '{sugg}'.",
        "affected_reports": ["REP-EXEC-HEADCOUNT"],
        "business_risk": "Data warehouse ETL pipeline failures, unassigned employees in executive headcount reports."
    })

# -------------------------------------------------------------
# Category 5: MISMATCHED DATES (Data Quality / Regulatory: Medium)
# Payroll hire date precedes Core HR hire date by years, or Hire > Term.
# -------------------------------------------------------------
date_mismatch_count = 35
selected_date_mismatch = random.sample(active_indices[1500:3000], date_mismatch_count)
for idx in selected_date_mismatch:
    emp = core_records[idx]
    pay = payroll_records[idx]
    # Shift payroll date 5 years earlier
    hr_hire = datetime.strptime(emp["hire_date"], "%Y-%m-%d")
    bogus_pay_hire = hr_hire - timedelta(days=1825)
    pay["effective_start_date"] = format_date_payroll(bogus_pay_hire)
    
    planted_errors.append({
        "issue_id": f"ERR-DATE-{emp['employee_id']}",
        "category": "DATE_MISMATCH",
        "severity": "MEDIUM",
        "primary_entity_id": emp["employee_id"],
        "entity_name": f"{emp['first_name']} {emp['last_name']}",
        "source_systems": ["core_hr", "payroll"],
        "description": f"Effective start date in Payroll ({pay['effective_start_date']}) is 5 years before official hire date in Core HR ({emp['hire_date']}).",
        "field_in_conflict": "hire_date vs effective_start_date",
        "current_values": {"core_hr.hire_date": emp["hire_date"], "payroll.effective_start_date": pay["effective_start_date"]},
        "suggested_fix": f"Align payroll effective start date to Core HR hire date: {format_date_payroll(hr_hire)}.",
        "affected_reports": ["REP-WPS-PAYROLL", "REP-EXEC-HEADCOUNT"],
        "business_risk": "End of Service Benefit (EOSB) calculation inaccuracies, regulatory labor audit discrepancies."
    })

# -------------------------------------------------------------
# Category 6: DUPLICATE EMPLOYEES (Fuzzy / Cross-ID Identity Duplication: High)
# Same person registered under 2 different EK IDs with minor spelling variation.
# -------------------------------------------------------------
duplicate_count = 30
selected_dups = random.sample(active_indices[3000:4500], duplicate_count)
for idx in selected_dups:
    orig = core_records[idx]
    dup_id = f"EK{20000 + idx}"
    # Slight typo in name (e.g. Ahmed -> Ahmd or Mohammed -> Mohamed)
    alt_first = orig["first_name"][:-1] if len(orig["first_name"]) > 4 else orig["first_name"] + "a"
    
    dup_core = dict(orig)
    dup_core["employee_id"] = dup_id
    dup_core["first_name"] = alt_first
    core_records.append(dup_core)
    
    planted_errors.append({
        "issue_id": f"ERR-DUP-{orig['employee_id']}-{dup_id}",
        "category": "DUPLICATE_ENTITY",
        "severity": "HIGH",
        "primary_entity_id": orig["employee_id"],
        "secondary_entity_id": dup_id,
        "entity_name": f"{orig['first_name']} {orig['last_name']} / {alt_first} {orig['last_name']}",
        "source_systems": ["core_hr"],
        "description": f"Potential duplicate employee records detected: {orig['employee_id']} and {dup_id} share identical National ID ({orig['national_id']}), Date of Birth ({orig['date_of_birth']}), and matching last name '{orig['last_name']}'.",
        "field_in_conflict": "identity_linkage",
        "current_values": {"primary_id": orig["employee_id"], "duplicate_id": dup_id, "shared_national_id": orig["national_id"]},
        "suggested_fix": f"Merge duplicate record {dup_id} into master record {orig['employee_id']}.",
        "affected_reports": ["REP-EXEC-HEADCOUNT"],
        "business_risk": "Inflated headcount, duplicate benefits provisioning, double IT license allocations."
    })

# -------------------------------------------------------------
# Category 7: MISSING MANDATORY / MALFORMED VALUES (Compliance: High)
# Missing IBAN on active payroll or corrupted IBAN format.
# -------------------------------------------------------------
missing_iban_count = 25
selected_missing_iban = random.sample(active_indices[100:1000], missing_iban_count)
for idx in selected_missing_iban:
    pay = payroll_records[idx]
    emp = core_records[idx]
    pay["bank_iban"] = ""  # Missing!
    planted_errors.append({
        "issue_id": f"ERR-NOIBAN-{emp['employee_id']}",
        "category": "MISSING_VALUE",
        "severity": "HIGH",
        "primary_entity_id": emp["employee_id"],
        "entity_name": f"{emp['first_name']} {emp['last_name']}",
        "source_systems": ["payroll"],
        "description": f"Active payroll employee {emp['employee_id']} ({pay['legal_name']}) is missing a bank IBAN.",
        "field_in_conflict": "bank_iban",
        "current_values": {"payroll.bank_iban": ""},
        "suggested_fix": "Request employee banking details via self-service portal before next payroll cutoff.",
        "affected_reports": ["REP-WPS-PAYROLL"],
        "business_risk": "WPS transaction rejection, employee salary payment failure."
    })

# Write CSV Files
print(f"Writing {len(core_records)} records to core_hr.csv...")
with open(os.path.join(RAW_DIR, "core_hr.csv"), "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=list(core_records[0].keys()))
    writer.writeheader()
    writer.writerows(core_records)

print(f"Writing {len(payroll_records)} records to payroll.csv...")
with open(os.path.join(RAW_DIR, "payroll.csv"), "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=list(payroll_records[0].keys()))
    writer.writeheader()
    writer.writerows(payroll_records)

print(f"Writing {len(learning_records)} records to learning.csv...")
with open(os.path.join(RAW_DIR, "learning.csv"), "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=list(learning_records[0].keys()))
    writer.writeheader()
    writer.writerows(learning_records)

print(f"Writing {len(directory_records)} records to access_directory.csv...")
with open(os.path.join(RAW_DIR, "access_directory.csv"), "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=list(directory_records[0].keys()))
    writer.writeheader()
    writer.writerows(directory_records)

# Write Ground Truth Key
with open(os.path.join(DATA_DIR, "ground_truth_errors.json"), "w", encoding="utf-8") as f:
    json.dump(planted_errors, f, indent=2)

# Write data_dictionary.md
data_dict_content = f"""# Emirates Group HR Data Quality Challenge - Data Dictionary

This document defines the fields, formats, systems of record, and valid reference code lists for the Emirates Group HR ecosystem.

---

## 1. Systems Overview

| System Name | System Role | Primary Identifier | Key Managed Attributes |
| :--- | :--- | :--- | :--- |
| **Core HR** | System of Record for master employment | `employee_id` (`EK#####`) | Master employment status, official grade, job title, department, hire/term dates, personal identity. |
| **Payroll** | Disbursement & UAE WPS Compliance | `payroll_id` (`PR-#####`) | Monthly basic salary, bank IBAN, cost centers, payment frequency, pay status. |
| **Learning (LMS)** | Training & Mandatory Certifications | `lms_user_id` (`LMS-#####`) | GCAA aviation safety certifications, recurrent flight crew training, learning tracks. |
| **Access Directory** | IT Identity & Access Management (IAM) | `samaccountname` | Corporate work email, active directory account status, security badge ID, last logon timestamp. |

---

## 2. Standard Reference Codes

### Departments (`department_code`)
- `EK-FLIGHT-OPS`: Flight Operations (Pilots & Flight Deck Crew)
- `EK-CABIN-CREW`: In-flight Service & Cabin Crew
- `EK-ENG`: Engineering, Line Maintenance & Fleet Airworthiness
- `EK-AIRPORT-SVCS`: Airport Operations, Passenger Terminal 3 Services
- `EK-COMMERCIAL`: Commercial Strategy, Revenue Optimization & Global Sales
- `EK-IT`: Group IT, Cloud Infrastructure & Digital Architecture
- `EK-HR`: Group Human Resources & Talent Management
- `DNATA-GROUND-SVCS`: Dnata Ground Operations, Ramp & Baggage
- `DNATA-CARGO`: Dnata Cargo Handling & Freight Logistics
- `DNATA-TRAVEL`: Dnata Retail, Corporate & Leisure Travel

### Job Grades (`job_grade`)
- Ground & Professional Staff: `G01` to `G12`
- Flight Deck & Cabin Technical: `CR01` to `CR06`
- Engineering & Aircraft Tech: `T01` to `T08`
- Executive Leadership: `E01` to `E05`

### Primary Work Locations (`work_location`)
- `DXB-HQ`: Emirates Group Headquarters, Dubai
- `DXB-T3`: Dubai International Airport Terminal 3
- `DWC-ALMAKTOUM`: Al Maktoum International Airport / Dubai South Hub
- `AUH-HUB`: Abu Dhabi International Hub
- `LHR-STATION`: London Heathrow Outstation
- `JFK-STATION`: New York JFK Outstation
- `SIN-STATION`: Singapore Changi Outstation

### Status Codes
- Core HR: `ACTIVE`, `ON_LEAVE`, `TERMINATED`, `RESIGNED`, `SUSPENDED`
- Payroll: `ACTIVE`, `INACTIVE`, `HOLD`
- Access Directory: `Active`, `Disabled`

### Format Standards
- Core HR Dates: `YYYY-MM-DD` (e.g. `2024-03-15`)
- Payroll Dates: `DD/MM/YYYY` (e.g. `15/03/2024`)
- Access Directory Timestamp: `YYYY-MM-DD HH:MM:SS`
- UAE IBAN: Standard 23-character format: `AE` + 2 check digits + 3 bank alphanumeric characters + 16 numeric digits.
"""

with open(os.path.join(RAW_DIR, "data_dictionary.md"), "w", encoding="utf-8") as f:
    f.write(data_dict_content)

# Write dependencies.md
dependencies_content = """# Emirates Group HR System Dependencies & Report Lineage

This document outlines the upstream and downstream data flows between HR applications and the critical executive and regulatory reports that depend on specific data fields.

---

## 1. System Integration Feeds (Data Flow DAG)

```mermaid
graph TD
    CORE[Core HR System] -->|Employee Onboarding & Grades| PAYROLL[Payroll System]
    CORE -->|Offboarding & Terminations| PAYROLL
    CORE -->|User Provisioning & Role Sync| AD[Access Directory / IAM]
    CORE -->|Termination Trigger & Deprovisioning| AD
    CORE -->|Employee Job Code & Role Mapping| LMS[Learning LMS]
    
    PAYROLL -->|Monthly Salary & IBAN Export| WPS[UAE Central Bank WPS Engine]
    LMS -->|Flight Crew Safety Certifications| GCAA[GCAA Flight Readiness Engine]
    
    CORE -->|Department & Active Headcount| REP1[REP-EXEC-HEADCOUNT]
    PAYROLL -->|Total Cost & Salary Disbursement| REP2[REP-WPS-PAYROLL]
    LMS -->|Safety Compliance Rate| REP3[REP-GCAA-SAFETY]
    AD -->|Dormant / Terminated Accounts| REP4[REP-SEC-OFFBOARDING]
    CORE -->|Training Budget Headcount| REP5[REP-LMS-BUDGET]
```

---

## 2. Downstream Reports & Field Dependencies

### REP-EXEC-HEADCOUNT: Executive Headcount & Emaratisation Dashboard
- **Executive Owner**: Chief Human Resources Officer & Group Executive Board
- **Critical Fields**:
  - `core_hr.employment_status`
  - `core_hr.department_code`
  - `core_hr.nationality`
  - `core_hr.work_location`
  - `core_hr.job_grade`
- **Downstream Impact**: Inaccurate headcount sizing, non-compliance with UAE National Emiratisation statutory quotas, board misreporting.

### REP-WPS-PAYROLL: Monthly Wages Protection System (WPS) File
- **Regulatory Authority**: UAE Ministry of Human Resources & Emiratisation (MOHRE) & UAE Central Bank
- **Critical Fields**:
  - `payroll.payroll_id`
  - `payroll.bank_iban`
  - `payroll.monthly_basic_aed`
  - `payroll.pay_status`
  - `core_hr.national_id`
  - `core_hr.employment_status`
- **Downstream Impact**: Bank transaction rejections, financial cash leakage on terminated staff, MOHRE regulatory compliance fines.

### REP-GCAA-SAFETY: GCAA Aviation Safety Compliance & Airworthiness Audit
- **Regulatory Authority**: UAE General Civil Aviation Authority (GCAA) & IATA
- **Critical Fields**:
  - `core_hr.job_title`
  - `core_hr.department_code`
  - `learning.aviation_safety_cert`
  - `learning.compliance_status`
- **Downstream Impact**: Grounding of aircraft, pilot scheduling non-compliance, regulatory audit citations.

### REP-SEC-OFFBOARDING: IT Security & Identity Offboarding Audit
- **Executive Owner**: Group Chief Information Security Officer (CISO)
- **Critical Fields**:
  - `core_hr.termination_date`
  - `core_hr.employment_status`
  - `access_directory.account_status`
  - `access_directory.last_logon_timestamp`
- **Downstream Impact**: Critical data breach, unauthorized access by ex-employees, ISO 27001 audit failure.

### REP-LMS-BUDGET: Group Learning & Development Budget Allocation
- **Executive Owner**: VP Talent & Development
- **Critical Fields**:
  - `learning.assigned_department`
  - `core_hr.job_grade`
  - `payroll.cost_center`
- **Downstream Impact**: Misallocated departmental training charges, inaccurate overhead cross-billing.
"""

with open(os.path.join(RAW_DIR, "dependencies.md"), "w", encoding="utf-8") as f:
    f.write(dependencies_content)

print(f"Successfully generated all files in {RAW_DIR}")
print(f"Total planted errors: {len(planted_errors)} recorded in {os.path.join(DATA_DIR, 'ground_truth_errors.json')}")
