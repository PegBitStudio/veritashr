"""
Unit and Integration Test Suite for VeritasHR Pipeline.
Verifies entity resolution, anomaly detection, blast radius simulation, and trust scores.
"""

import os
import pytest
from src.pipeline import VeritasHRPipeline
from src.matching.record_linker import normalize_name, jaro_winkler_similarity
from src.models.issue import Severity, IssueCategory

@pytest.fixture(scope="module")
def pipeline_runner():
    base_dir = os.path.dirname(os.path.dirname(__file__))
    raw_path = os.path.join(base_dir, "data", "raw")
    pipeline = VeritasHRPipeline(raw_path)
    results = pipeline.run()
    return pipeline, results

def test_name_normalization():
    assert normalize_name("AL MANSOORI, AHMED") == "ahmed al mansoori"
    assert normalize_name("Ahmed Al-Mansoori!") == "ahmed almansoori"
    assert normalize_name("Sarah Smith") == "sarah smith"

def test_jaro_winkler():
    sim1 = jaro_winkler_similarity("Ahmed Al Mansoori", "Ahmed Al Mansoori")
    assert sim1 == 1.0
    sim2 = jaro_winkler_similarity("Ahmed Al Mansoori", "Ahmd Al Mansoori")
    assert sim2 > 0.95
    sim3 = jaro_winkler_similarity("Ahmed", "Zainab")
    assert sim3 < 0.5

def test_pipeline_execution(pipeline_runner):
    pipeline, results = pipeline_runner
    assert len(results["golden_records"]) >= 5000
    assert len(results["issues"]) > 200
    assert 0.0 <= results["trust_scores"]["global_trust_score"] <= 100.0

def test_ghost_payroll_detection(pipeline_runner):
    pipeline, results = pipeline_runner
    ghosts = [i for i in results["issues"] if i.category == IssueCategory.GHOST_RECORD]
    assert len(ghosts) >= 30
    for g in ghosts:
        assert g.severity == Severity.CRITICAL
        assert g.financial_risk_aed > 0
        assert "REP-WPS-PAYROLL" in g.affected_reports

def test_zombie_accounts_detection(pipeline_runner):
    pipeline, results = pipeline_runner
    zombies = [i for i in results["issues"] if i.category == IssueCategory.SECURITY_EXPOSURE]
    assert len(zombies) >= 30
    for z in zombies:
        assert z.severity == Severity.HIGH
        assert "REP-SEC-OFFBOARDING" in z.affected_reports

def test_duplicate_entity_detection(pipeline_runner):
    pipeline, results = pipeline_runner
    duplicates = [i for i in results["issues"] if i.category == IssueCategory.DUPLICATE_ENTITY]
    assert len(duplicates) >= 20

def test_submission_csv_export(pipeline_runner, tmp_path):
    pipeline, results = pipeline_runner
    test_out = str(tmp_path / "test_issue_list.csv")
    pipeline.export_submission_csv(test_out)
    assert os.path.exists(test_out)
    assert os.path.getsize(test_out) > 5000
