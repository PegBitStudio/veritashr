"""A new, unknown HR system dropped into the data folder is onboarded and checked with no code changes."""

import io
import os
import csv
import random
import shutil
import contextlib
import pytest
from src.pipeline import VeritasHRPipeline

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

@pytest.fixture(scope="module")
def run(tmp_path_factory):
    random.seed(1)
    t = str(tmp_path_factory.mktemp("fifth"))
    for f in os.listdir(os.path.join(BASE, "data", "raw")):
        shutil.copy(os.path.join(BASE, "data", "raw", f), t)
    with open(os.path.join(BASE, "data", "raw", "core_hr.csv"), encoding="utf-8") as f:
        core = list(csv.DictReader(f))
    with open(os.path.join(BASE, "data", "ground_truth_errors.json"), encoding="utf-8") as f:
        dirty = {e["primary_entity_id"] for e in __import__("json").load(f)}
    clean = [r for r in core if r["employee_id"] not in dirty][:3000]
    rows = [{"Staff Number": r["employee_id"].replace("EK", ""), "Employee Name": f"{r['first_name']} {r['last_name']}",
             "Dept": r["department_code"], "Shift Status": r["employment_status"].title(), "Joined On": r["hire_date"]} for r in clean]
    planted = {}
    for i, r in enumerate(random.sample([x for x in rows if x["Shift Status"] == "Active"], 12)):
        eid = "EK" + r["Staff Number"]
        if i % 3 == 0:
            r["Dept"] = "EK-IT" if r["Dept"] != "EK-IT" else "EK-HR"; planted[eid] = "DEPARTMENT_CONFLICT"
        elif i % 3 == 1:
            r["Joined On"] = "2001-01-01"; planted[eid] = "DATE_MISMATCH"
        else:
            r["Shift Status"] = "Terminated"; planted[eid] = "STATUS_CONFLICT"
    rows.append({"Staff Number": "99999", "Employee Name": "Nobody Known", "Dept": "EK-IT", "Shift Status": "Active", "Joined On": "2020-01-01"})
    planted["99999"] = "GHOST_RECORD"
    with open(os.path.join(t, "time_attendance.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    p = VeritasHRPipeline(t)
    with contextlib.redirect_stdout(io.StringIO()):
        p.run()
    return p, planted

def test_new_system_is_mapped(run):
    p, _ = run
    mapped = {c: m["source_column"] for c, m in p.loader.mapper.report["timeattendance"]["mapped"].items()}
    assert mapped["employee_ref"] == "Staff Number" and mapped["employment_status"] == "Shift Status" and mapped["hire_date"] == "Joined On"

def test_new_system_conflicts_found_without_false_alarms(run):
    p, planted = run
    found = {(i.primary_entity_id, i.category.value) for i in p.issues if "timeattendance" in i.source_systems}
    assert set(planted.items()) <= found
    assert len(found - set(planted.items())) == 0
