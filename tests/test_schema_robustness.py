"""
Robustness tests: the pipeline must give the same answers when source files arrive
with different names, columns, delimiters, date formats, status words and ID formats.
"""

import io
import os
import sys
import contextlib
import subprocess
import pytest
from src.pipeline import VeritasHRPipeline
from src.ingestion.schema_mapper import parse_any_date, SchemaMapper, normalize_id

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GT = os.path.join(BASE, "data", "ground_truth_errors.json")

@pytest.fixture(scope="module")
def messy_metrics(tmp_path_factory):
    out = str(tmp_path_factory.mktemp("messy"))
    subprocess.run([sys.executable, os.path.join(BASE, "scripts", "make_messy_variant.py"),
                    os.path.join(BASE, "data", "raw"), out], check=True, capture_output=True)
    p = VeritasHRPipeline(out)
    with contextlib.redirect_stdout(io.StringIO()):
        p.run()
    return p, p.evaluate_benchmark(GT)

def test_messy_files_discovered_and_mapped(messy_metrics):
    p, _ = messy_metrics
    rep = p.loader.mapper.report
    assert rep["core_hr"]["file"] == "HR_Master_Extract.csv"
    assert rep["payroll"]["mapped"]["employee_ref"]["source_column"] == "Staff No"
    assert rep["payroll"]["mapped"]["bank_iban"]["source_column"] == "IBAN"
    assert rep["access_directory"]["mapped"]["account_status"]["source_column"] == "Enabled"

def test_messy_accuracy_matches_clean(messy_metrics):
    _, m = messy_metrics
    assert m["false_negatives"] <= 2
    assert m["false_positives"] <= 3

def test_name_only_payroll_rows_are_linked(messy_metrics):
    p, _ = messy_metrics
    assert len(p.resolver.unlinked.get("payroll", [])) == 0
    methods = {g.link_methods.get("payroll", "") for g in p.golden_records.values()}
    assert any(m.startswith(("exact_name", "name+")) for m in methods)

def test_date_parsing_formats():
    for v in ("2024-03-15", "15/03/2024", "15-Mar-2024", "2024/03/15", "2024-03-15 10:00:00", "2024-03-15T10:00:00Z"):
        assert parse_any_date(v).strftime("%Y-%m-%d") == "2024-03-15", v
    assert parse_any_date("N/A") is None

def test_id_normalization():
    assert normalize_id(" ek-10001 ") == "EK10001"

def test_status_vocabulary_normalized(tmp_path):
    m = SchemaMapper(str(tmp_path))
    rows = m.canonicalize("payroll", [{"Pay ID": "P1", "Payment Status": "On Hold"}, {"Pay ID": "P2", "Payment Status": "paid"}])
    assert [r["pay_status"] for r in rows] == ["HOLD", "ACTIVE"]


@pytest.fixture(scope="module")
def blind_run(tmp_path_factory):
    out = str(tmp_path_factory.mktemp("blind"))
    subprocess.run([sys.executable, os.path.join(BASE, "scripts", "inject_blind_errors.py"),
                    os.path.join(BASE, "data", "raw"), out], check=True, capture_output=True)
    p = VeritasHRPipeline(out)
    with contextlib.redirect_stdout(io.StringIO()):
        p.run()
    import json
    with open(os.path.join(out, "blind_answer_key.json")) as f:
        key = json.load(f)
    with open(GT) as f:
        base = {(e["primary_entity_id"], e["category"]) for e in json.load(f)}
    return p, key, base

def test_blind_new_error_types_all_found(blind_run):
    p, key, _ = blind_run
    det = {(i.primary_entity_id, i.category.value) for i in p.issues}
    missed = [k for k in key if (k["primary_entity_id"], k["category"]) not in det]
    assert not missed, missed

def test_blind_no_knock_on_false_positives(blind_run):
    p, key, base = blind_run
    expected = base | {(k["primary_entity_id"], k["category"]) for k in key}
    extra = [i.issue_id for i in p.issues if (i.primary_entity_id, i.category.value) not in expected]
    assert len(extra) <= 2, extra
