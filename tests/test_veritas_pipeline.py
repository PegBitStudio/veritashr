"""
Automated Test Suite for VeritasHR Pipeline using Python's standard unittest.
"""

import os
import tempfile
import unittest
from src.pipeline import VeritasHRPipeline
from src.matching.record_linker import normalize_name, jaro_winkler_similarity
from src.models.issue import Severity, IssueCategory

class TestVeritasHRPipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        base_dir = os.path.dirname(os.path.dirname(__file__))
        raw_path = os.path.join(base_dir, "data", "raw")
        cls.pipeline = VeritasHRPipeline(raw_path)
        cls.results = cls.pipeline.run()

    def test_name_normalization(self):
        self.assertEqual(normalize_name("AL MANSOORI, AHMED"), "ahmed al mansoori")
        self.assertEqual(normalize_name("Ahmed Al-Mansoori!"), "ahmed almansoori")
        self.assertEqual(normalize_name("Sarah Smith"), "sarah smith")

    def test_jaro_winkler(self):
        sim1 = jaro_winkler_similarity("Ahmed Al Mansoori", "Ahmed Al Mansoori")
        self.assertEqual(sim1, 1.0)
        sim2 = jaro_winkler_similarity("Ahmed Al Mansoori", "Ahmd Al Mansoori")
        self.assertGreater(sim2, 0.95)
        sim3 = jaro_winkler_similarity("Ahmed", "Zainab")
        self.assertLess(sim3, 0.5)

    def test_golden_records_resolved(self):
        self.assertGreaterEqual(len(self.results["golden_records"]), 5000)

    def test_issues_detected(self):
        self.assertGreaterEqual(len(self.results["issues"]), 200)

    def test_ghost_payroll_detected(self):
        ghosts = [i for i in self.results["issues"] if i.category == IssueCategory.GHOST_RECORD]
        self.assertGreaterEqual(len(ghosts), 30)
        for g in ghosts:
            self.assertEqual(g.severity, Severity.CRITICAL)
            self.assertGreater(g.financial_risk_aed, 0)
            self.assertIn("REP-WPS-PAYROLL", g.affected_reports)

    def test_zombie_accounts_detected(self):
        zombies = [i for i in self.results["issues"] if i.category == IssueCategory.SECURITY_EXPOSURE]
        self.assertGreaterEqual(len(zombies), 30)
        for z in zombies:
            self.assertEqual(z.severity, Severity.HIGH)
            self.assertIn("REP-SEC-OFFBOARDING", z.affected_reports)

    def test_department_conflicts_detected(self):
        dept_issues = [i for i in self.results["issues"] if i.category == IssueCategory.DEPARTMENT_CONFLICT]
        self.assertGreaterEqual(len(dept_issues), 40)

    def test_invalid_codes_detected(self):
        code_issues = [i for i in self.results["issues"] if i.category == IssueCategory.INVALID_CODE]
        self.assertGreaterEqual(len(code_issues), 30)

    def test_trust_scores_valid(self):
        g_score = self.results["trust_scores"]["global_trust_score"]
        self.assertTrue(0.0 <= g_score <= 100.0)

    def test_csv_export(self):
        test_out = os.path.join(tempfile.mkdtemp(), "test_issue_list.csv")
        self.pipeline.export_submission_csv(test_out)
        self.assertTrue(os.path.exists(test_out))
        self.assertGreater(os.path.getsize(test_out), 5000)
        if os.path.exists(test_out):
            os.remove(test_out)

if __name__ == "__main__":
    unittest.main()
