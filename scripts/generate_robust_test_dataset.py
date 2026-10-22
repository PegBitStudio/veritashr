"""
Generates a highly robust, realistic test dataset with edge cases for live end-to-end testing.
Creates messy column headers, varied date formats, and seeded real-world airline HR anomalies.
"""

import os
import csv
import random
from datetime import datetime, timedelta

random.seed(999)
TEST_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "robust_test")
os.makedirs(TEST_DIR, exist_ok=True)

# 1. Generate Core HR (1,000 employees + tricky edge cases)
core_rows = []
for i in range(1, 1001):
    ek_id = f"EK{30000 + i}"
    gender = "M" if i % 2 == 0 else "F"
    fname = "Mohammed" if gender == "M" else "Fatima"
    lname = "Al Mansoori" if i % 3 == 0 else "Smith" if i % 3 == 1 else "Khan"
    dept = "EK-FLIGHT-OPS" if i % 5 == 0 else "EK-CABIN-CREW" if i % 5 == 1 else "EK-ENG" if i % 5 == 2 else "EK-IT" if i % 5 == 3 else "DNATA-GROUND-SVCS"
    grade = "CR05" if dept == "EK-FLIGHT-OPS" else "CR02" if dept == "EK-CABIN-CREW" else "T04" if dept == "EK-ENG" else "G07"
    title = "A380 Captain" if dept == "EK-FLIGHT-OPS" else "Purser" if dept == "EK-CABIN-CREW" else "Aircraft Engineer" if dept == "EK-ENG" else "Engineer"
    loc = "DXB-T3" if dept in ("EK-CABIN-CREW", "DNATA-GROUND-SVCS") else "DXB-HQ"
    
    is_term = (i % 15 == 0)
    status = "TERMINATED" if is_term else "ACTIVE"
    hire_dt = datetime(2015, 1, 1) + timedelta(days=(i * 3) % 2500)
    term_dt = hire_dt + timedelta(days=1200) if is_term else None
    
    core_rows.append({
        "Emp_ID": ek_id,
        "Given_Name": fname,
        "Family_Name": lname,
        "DOB": (datetime(1975, 1, 1) + timedelta(days=(i * 11) % 8000)).strftime("%d/%m/%Y"),
        "Gender": gender,
        "Nationality_Code": "AE" if i % 2 == 0 else "GB",
        "Emirates_ID": f"784-1980-{3000000+i:07d}-1",
        "Passport_No": f"P{8000000+i}",
        "Department_Code": dept,
        "Job_Title": title,
        "Job_Grade": grade,
        "Work_Location": loc,
        "Employment_Status": status,
        "Hire_Date": hire_dt.strftime("%Y-%m-%d"),
        "Termination_Date": term_dt.strftime("%Y-%m-%d") if term_dt else ""
    })

# Add Edge Case 1: High-earning Flight Captain terminated, but still active in Payroll
core_rows[14]["Employment_Status"] = "TERMINATED"
core_rows[14]["Termination_Date"] = "2024-03-15"
ghost_emp_id = core_rows[14]["Emp_ID"]

# Add Edge Case 2: Re-hired Duplicate Purser
dup_purser = dict(core_rows[50])
dup_purser["Emp_ID"] = "EK99999"
dup_purser["Given_Name"] = "Fatma"  # spelling variant
core_rows.append(dup_purser)

# Add Edge Case 3: Date Paradox (Hire > Term)
core_rows[30]["Hire_Date"] = "2024-10-01"
core_rows[30]["Termination_Date"] = "2024-05-01"
core_rows[30]["Employment_Status"] = "TERMINATED"

# Add Edge Case 4: Invalid Department Code
core_rows[40]["Department_Code"] = "EK-FLT-OPS"  # typo for EK-FLIGHT-OPS

# Write core_hr.csv
with open(os.path.join(TEST_DIR, "core_hr.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(core_rows[0].keys()))
    w.writeheader()
    w.writerows(core_rows)

# 2. Generate Payroll (Messy header aliases)
payroll_rows = []
for i, emp in enumerate(core_rows[:1000]):
    ek_id = emp["Emp_ID"]
    salary = 68000.0 if "Captain" in emp["Job_Title"] else 24000.0 if "Purser" in emp["Job_Title"] else 18000.0
    pay_status = "ACTIVE"
    if emp["Employment_Status"] == "TERMINATED" and ek_id != ghost_emp_id:
        pay_status = "INACTIVE"
    
    iban = f"AE02ENBD{9000000000000000 + i}"
    if i == 25:
        iban = ""  # Missing IBAN for active payee!
        
    payroll_rows.append({
        "Payroll_Record_ID": f"PR-{70000 + i}",
        "Staff_Ref_Number": ek_id,
        "Payee_Full_Name": f"{emp['Family_Name'].upper()}, {emp['Given_Name'].upper()}",
        "Bank_IBAN_Code": iban,
        "Bank_Name": "Emirates NBD",
        "Monthly_Basic_AED": salary,
        "Currency": "AED",
        "Cost_Center_Code": f"CC-{emp['Department_Code']}",
        "Pay_Status": pay_status,
        "Effective_Date": "01/01/2020"
    })

# Add Cost Center Conflict
payroll_rows[70]["Cost_Center_Code"] = "CC-EK-COMMERCIAL" # Mismatched cost center!

with open(os.path.join(TEST_DIR, "payroll_export.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(payroll_rows[0].keys()))
    w.writeheader()
    w.writerows(payroll_rows)

# 3. Generate Learning (LMS)
learning_rows = []
for i, emp in enumerate(core_rows[:1000]):
    ek_id = emp["Emp_ID"]
    cert = "VALID" if "Captain" in emp["Job_Title"] or "Purser" in emp["Job_Title"] else "N/A"
    compliance = "COMPLIANT"
    
    # Add Edge Case: Active Captain with EXPIRED aviation safety certificate!
    if i == 5 and "Captain" in emp["Job_Title"]:
        cert = "EXPIRED"
        compliance = "NON-COMPLIANT"
        
    learning_rows.append({
        "Learner_ID": f"LMS-{50000 + i}",
        "Employee_Number": ek_id,
        "Learner_Name": f"{emp['Given_Name']} {emp['Family_Name']}",
        "Department": emp["Department_Code"],
        "Role_Title": emp["Job_Title"],
        "GCAA_Safety_Cert": cert,
        "Last_Training_Date": "2023-11-15",
        "Training_Status": compliance
    })

with open(os.path.join(TEST_DIR, "lms_certifications.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(learning_rows[0].keys()))
    w.writeheader()
    w.writerows(learning_rows)

# 4. Generate Access Directory (IAM)
ad_rows = []
for i, emp in enumerate(core_rows[:1000]):
    ek_id = emp["Emp_ID"]
    uname = f"{emp['Given_Name'].lower()}.{emp['Family_Name'].lower().replace(' ', '')}{i}"
    ad_status = "Disabled" if emp["Employment_Status"] == "TERMINATED" else "Active"
    last_logon = "2024-10-18 09:15:00"
    
    # Add Edge Case: Zombie login (terminated employee with Active login yesterday!)
    if i == 29: # Terminated employee
        ad_status = "Active"
        last_logon = "2024-10-21 22:45:00"
        
    ad_rows.append({
        "UserName": uname,
        "Email_Address": f"{uname}@emirates.group",
        "Staff_ID": ek_id,
        "Display_Name": f"{emp['Given_Name']} {emp['Family_Name']}",
        "Account_Enabled": ad_status,
        "Access_Card_Badge": f"BDG-{90000 + i}",
        "Last_Sign_In_Timestamp": last_logon
    })

with open(os.path.join(TEST_DIR, "active_directory.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(ad_rows[0].keys()))
    w.writeheader()
    w.writerows(ad_rows)

# Copy data_dictionary.md and dependencies.md
import shutil
base_raw = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "raw")
shutil.copy(os.path.join(base_raw, "data_dictionary.md"), os.path.join(TEST_DIR, "data_dictionary.md"))
shutil.copy(os.path.join(base_raw, "dependencies.md"), os.path.join(TEST_DIR, "dependencies.md"))

print(f"Successfully generated robust test dataset in: {TEST_DIR}")
