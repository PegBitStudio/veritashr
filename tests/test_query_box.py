"""'Ask HR Truth' answers must be correct, show their interpretation and sources, and never guess."""

import io
import os
import contextlib
import pytest
from src.pipeline import VeritasHRPipeline
from src.qa.query_box import AskHRTruthEngine

@pytest.fixture(scope="module")
def engine():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    p = VeritasHRPipeline(os.path.join(base, "data", "raw"))
    with contextlib.redirect_stdout(io.StringIO()):
        r = p.run()
    return AskHRTruthEngine(r["golden_records"], r["issues"], p.loader.catalog), r["golden_records"]

def test_dubai_count_matches_records(engine):
    q, golden = engine
    expected = sum(1 for g in golden.values() if g.employment_status == "ACTIVE" and g.work_location in {"DXB-HQ", "DXB-T3", "DWC-ALMAKTOUM"})
    a = q.answer_query("How many active employees in Dubai?")
    assert a["headline_answer"].startswith(f"{expected:,}")
    assert "Core HR" in a["authoritative_source"] and "location" in a["interpretation"]

def test_salary_question_uses_payroll(engine):
    a = engine[0].answer_query("Total monthly salary for cabin crew")
    assert a["headline_answer"].startswith("AED") and "Payroll" in a["authoritative_source"]

def test_unknown_question_is_not_guessed(engine):
    a = engine[0].answer_query("what is the weather tomorrow")
    assert a["headline_answer"].startswith("Sorry")
