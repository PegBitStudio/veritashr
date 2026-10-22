"""
Builds a deliberately "messy" copy of a dataset to stress-test schema auto-mapping.

Same people and same planted errors, but with:
  - different file names, delimiters and column order
  - renamed columns (e.g. employee_id -> "Emp No", bank_iban -> "IBAN")
  - different date formats, status vocabularies and ID formats
  - payroll employee references removed for a share of rows (forces name matching)

Usage: python scripts/make_messy_variant.py [src_dir] [out_dir]
"""

import os
import sys
import csv
import random
import shutil
from datetime import datetime

random.seed(7)
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(BASE, "data", "raw")
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(BASE, "data", "variants", "messy")

def read(name):
    with open(os.path.join(SRC, name), encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))

def write(name, rows, delimiter=","):
    cols = list(rows[0].keys())
    random.shuffle(cols)
    with open(os.path.join(OUT, name), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, delimiter=delimiter)
        w.writeheader()
        w.writerows(rows)

def iso_to(v, fmt):
    if not v:
        return v
    for src_fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(v, src_fmt).strftime(fmt)
        except ValueError:
            pass
    return v

os.makedirs(OUT, exist_ok=True)
for f in ("data_dictionary.md", "dependencies.md"):
    if os.path.exists(os.path.join(SRC, f)):
        shutil.copy(os.path.join(SRC, f), OUT)

core_status = {"ACTIVE": "Active", "TERMINATED": "Terminated", "RESIGNED": "Resigned", "ON_LEAVE": "On Leave", "SUSPENDED": "Suspended"}
core = [{
    "Emp No": r["employee_id"],
    "Employee Name": f"{r['last_name']}, {r['first_name']}",
    "DOB": iso_to(r["date_of_birth"], "%d-%b-%Y"),
    "Sex": r["gender"],
    "Citizenship": r["nationality"],
    "Emirates ID": r["national_id"],
    "Passport No": r["passport_number"],
    "Dept": r["department_code"].lower(),
    "Position": r["job_title"],
    "Grade": r["job_grade"],
    "Station": r["work_location"],
    "Status": core_status.get(r["employment_status"], r["employment_status"]),
    "Date of Joining": iso_to(r["hire_date"], "%d/%m/%Y"),
    "Leaving Date": iso_to(r["termination_date"], "%d/%m/%Y"),
} for r in read("core_hr.csv")]
write("HR_Master_Extract.csv", core)

pay_status = {"ACTIVE": "Paid", "INACTIVE": "Stopped", "HOLD": "On Hold"}
payroll = []
for r in read("payroll.csv"):
    ref = r["employee_ref"]
    roll = random.random()
    staff_no = "" if roll < 0.10 else ref.replace("EK", "") if roll < 0.60 else ref
    sal = r["monthly_basic_aed"]
    payroll.append({
        "Pay ID": r["payroll_id"],
        "Staff No": staff_no,
        "Payee Name": r["legal_name"],
        "IBAN": " ".join(r["bank_iban"][i:i + 4] for i in range(0, len(r["bank_iban"]), 4)),
        "Bank": r["bank_name"],
        "Basic Salary": f"AED {float(sal):,.0f}" if sal else "",
        "Ccy": r["currency"],
        "Cost Centre": r["cost_center"],
        "Payment Status": pay_status.get(r["pay_status"], r["pay_status"]),
        "Effective Date": iso_to(r["effective_start_date"], "%Y/%m/%d"),
    })
write("Payroll_Export_Oct.csv", payroll, delimiter=";")

lms = [{
    "Learner ID": r["lms_user_id"],
    "Employee ID": r["emp_core_id"].lower(),
    "Learner Name": r["full_name"],
    "Department": r["assigned_department"],
    "Role": r["job_role"],
    "GCAA Cert": r["aviation_safety_cert"],
    "Completion Date": r["last_training_date"],
    "Compliance": r["compliance_status"],
} for r in read("learning.csv")]
write("lms_profiles.csv", lms)

ad = [{
    "UserName": r["samaccountname"],
    "Mail": r["work_email"],
    "EmployeeID": r["employee_number"],
    "DisplayName": r["display_name"],
    "Enabled": "TRUE" if r["account_status"] == "Active" else "FALSE",
    "Badge": r["badge_id"],
    "LastLogon": r["last_logon_timestamp"],
} for r in read("access_directory.csv")]
write("AD_users_export.csv", ad)

print(f"Messy variant written to {OUT}")
