"""
Blind-test generator: plants error types that the original mock generator never produced,
into a copy of a dataset, and writes a separate answer key.

This checks that detection generalises beyond the patterns VeritasHR was developed on.

Usage: python scripts/inject_blind_errors.py [src_dir] [out_dir]
Writes <out_dir>/*.csv, the data dictionary / dependencies, and <out_dir>/blind_answer_key.json
"""

import os
import sys
import csv
import json
import random
import shutil

random.seed(2026)
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(BASE, "data", "raw")
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(BASE, "data", "variants", "blind")
PER_TYPE = 8

def read(name):
    with open(os.path.join(SRC, name), encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    return rows, list(rows[0].keys())

def write(name, rows, cols):
    with open(os.path.join(OUT, name), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)

os.makedirs(OUT, exist_ok=True)
for f in ("data_dictionary.md", "dependencies.md"):
    shutil.copy(os.path.join(SRC, f), OUT)

core, core_cols = read("core_hr.csv")
pay, pay_cols = read("payroll.csv")
lms, lms_cols = read("learning.csv")
ad, ad_cols = read("access_directory.csv")

# Only touch clean, active, fully-linked employees so planted errors don't overlap existing ones
with open(os.path.join(BASE, "data", "ground_truth_errors.json"), encoding="utf-8") as f:
    already = {e["primary_entity_id"] for e in json.load(f)}
pay_by = {r["employee_ref"]: r for r in pay}
lms_by = {r["emp_core_id"]: r for r in lms}
ad_by = {r["employee_number"]: r for r in ad}
pool = [r for r in core if r["employment_status"] == "ACTIVE" and r["employee_id"] not in already
        and r["employee_id"] in pay_by and r["employee_id"] in lms_by and r["employee_id"] in ad_by]
random.shuffle(pool)
take = iter(pool)
key = []

def plant(category, kind, emp, note):
    key.append({"primary_entity_id": emp, "category": category, "kind": kind, "note": note})

for _ in range(PER_TYPE):
    # 1. Job role conflict between Core HR and LMS
    r = next(take); e = r["employee_id"]
    lms_by[e]["job_role"] = "Senior Revenue Analyst" if "Pilot" in r["job_title"] or "Captain" in r["job_title"] else "Airline Captain"
    plant("JOB_CONFLICT", "lms_job_role", e, "LMS role differs from Core HR title")

    # 2. Termination date before hire date
    r = next(take); e = r["employee_id"]
    r["employment_status"] = "TERMINATED"; y = int(r["hire_date"][:4]) - 2
    r["termination_date"] = f"{y}{r['hire_date'][4:]}"
    pay_by[e]["pay_status"] = "INACTIVE"; ad_by[e]["account_status"] = "Disabled"
    plant("DATE_MISMATCH", "term_before_hire", e, "termination precedes hire")

    # 3. Missing Emirates ID in Core HR
    r = next(take); e = r["employee_id"]
    r["national_id"] = ""
    plant("MISSING_VALUE", "missing_national_id", e, "blank national_id")

    # 4. Malformed IBAN
    r = next(take); e = r["employee_id"]
    pay_by[e]["bank_iban"] = pay_by[e]["bank_iban"].replace("AE", "AF", 1)[:-3]
    plant("INVALID_CODE", "bad_iban", e, "IBAN wrong country code and length")

    # 5. Active in HR, inactive in payroll
    r = next(take); e = r["employee_id"]
    pay_by[e]["pay_status"] = "INACTIVE"
    plant("STATUS_CONFLICT", "active_not_paid", e, "active employee stopped on payroll")

    # 6. Double payroll record
    r = next(take); e = r["employee_id"]
    dup = dict(pay_by[e]); dup["payroll_id"] = "PR-" + str(99000 + len(key))
    pay.append(dup)
    plant("DUPLICATE_ENTITY", "double_pay", e, "second active payroll record")

    # 7. Name conflict on same ID (payroll points to another person)
    r = next(take); e = r["employee_id"]
    pay_by[e]["legal_name"] = "OKONKWO, CHIDINMA"
    plant("NAME_CONFLICT", "payroll_name", e, "payroll name is a different person")

    # 8. Orphan payee with no Core HR record
    ghost_ref = f"EK{88000 + len(key)}"
    pay.append({**pay[0], "payroll_id": f"PR-{98000 + len(key)}", "employee_ref": ghost_ref,
                "legal_name": f"PHANTOM, PAYEE{len(key)}", "pay_status": "ACTIVE"})
    plant("GHOST_RECORD", "orphan_payee", ghost_ref, "payee not in Core HR")

    # 9. Fuzzy duplicate identity (typo in name, same DOB/gender, new ID)
    r = next(take); e = r["employee_id"]
    twin = dict(r); twin["employee_id"] = f"EK{77000 + len(key)}"
    twin["last_name"] = r["last_name"][:-1] + ("a" if r["last_name"][-1] != "a" else "e")
    twin["national_id"] = ""; twin["passport_number"] = ""
    core.append(twin)
    plant("DUPLICATE_ENTITY", "fuzzy_duplicate", min(e, twin["employee_id"]), "typo twin")

    # 10. Expired safety training on active flight-ops employee
    r = next(take); e = r["employee_id"]
    r["department_code"] = "EK-FLIGHT-OPS"
    pay_by[e]["cost_center"] = "CC-EK-FLIGHT-OPS"; lms_by[e]["assigned_department"] = "EK-FLIGHT-OPS"
    ad_by[e]["display_name"] = ad_by[e]["display_name"].split(" (")[0] + " (EK-FLIGHT-OPS)"
    lms_by[e]["compliance_status"] = "EXPIRED"
    plant("REGULATORY_DEFICIT", "expired_cert", e, "active flight ops with expired training")

write("core_hr.csv", core, core_cols)
write("payroll.csv", pay, pay_cols)
write("learning.csv", lms, lms_cols)
write("access_directory.csv", ad, ad_cols)
with open(os.path.join(OUT, "blind_answer_key.json"), "w", encoding="utf-8") as f:
    json.dump(key, f, indent=2)
print(f"Planted {len(key)} new-type errors in {OUT}")
