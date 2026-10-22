"""
End-to-End Orchestrator Pipeline for VeritasHR.
Executes multi-source ingestion, entity resolution, anomaly detection,
blast-radius simulation, trust scoring, and competition issue list export.
"""

import os
import csv
import json
from typing import Dict, List, Any
from src.ingestion.loader import DataLoader
from src.matching.record_linker import EntityResolver
from src.anomaly.detector import AnomalyDetector
from src.impact.blast_radius import BlastRadiusSimulator
from src.trust.calculator import TrustScoreCalculator

class VeritasHRPipeline:
    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        self.loader = DataLoader(data_dir)
        self.resolver = EntityResolver()
        self.detector = AnomalyDetector(self.loader.catalog)
        self.simulator = BlastRadiusSimulator(self.loader.dependencies)
        self.trust_calc = TrustScoreCalculator(self.loader.dependencies.get("reports", {}))
        
        # State
        self.sources: Dict[str, List[Dict[str, Any]]] = {}
        self.golden_records: Dict[str, Any] = {}
        self.issues: List[Any] = []
        self.trust_scores: Dict[str, Any] = {}

    def run(self) -> Dict[str, Any]:
        """Runs the complete reconciliation pipeline."""
        print("[1/5] Ingesting multi-source HR files and schemas...")
        self.sources = self.loader.load_all_sources()
        for system, rep in self.loader.mapper.report.items():
            renamed = {c: m["source_column"] for c, m in rep["mapped"].items() if m["method"] != "exact"}
            if renamed:
                print(f"      [{system}] {rep.get('file')}: auto-mapped columns {renamed}")
        print(f"      Loaded: {len(self.sources['core_hr'])} Core HR, {len(self.sources['payroll'])} Payroll, {len(self.sources['learning'])} LMS, {len(self.sources['access_directory'])} Directory records.")

        print("[2/5] Performing Cross-System Entity Resolution & Identity Linking...")
        self.golden_records = self.resolver.resolve_identities(self.sources)
        print(f"      Resolved {len(self.golden_records)} canonical Golden Employee Records.")
        print(f"      Found {len(self.resolver.duplicate_pairs)} potential duplicate identity clusters.")
        unlinked = {k: len(v) for k, v in self.resolver.unlinked.items() if v}
        if unlinked:
            print(f"      Records matching no Core HR employee: {unlinked}")

        self.detector.reference_date = self._data_reference_date()
        print("[3/5] Executing Multi-Category Anomaly Detection Suite...")
        raw_issues = self.detector.detect_all_anomalies(
            self.golden_records,
            self.sources,
            self.resolver.duplicate_pairs,
            self.resolver.unlinked,
            self.resolver.multi_links
        )
        extras = getattr(self.loader, "extra_sources", {})
        if extras:
            from src.anomaly.extra_sources import check_extra_source
            for system, rows in extras.items():
                found = check_extra_source(system, rows, self.resolver, self.golden_records, self.loader.catalog)
                print(f"      Extra source '{system}' ({len(rows)} records) onboarded automatically: {len(found)} issues.")
                raw_issues = raw_issues + found
        print(f"      Detected {len(raw_issues)} quality inconsistencies.")

        print("[4/5] Simulating Downstream Blast Radius & Business Impact Scoring...")
        for issue in raw_issues:
            self.simulator.simulate_impact(issue)
            
        # Rank strictly by Business Impact Score descending
        self.issues = sorted(raw_issues, key=lambda x: x.impact_score, reverse=True)
        print(f"      Prioritized issues: {sum(1 for i in self.issues if i.severity == 'CRITICAL')} Critical, {sum(1 for i in self.issues if i.severity == 'HIGH')} High, {sum(1 for i in self.issues if i.severity == 'MEDIUM')} Medium.")

        print("[5/5] Calculating Data Trust Scores across systems and reports...")
        self.trust_scores = self.trust_calc.compute_all_trust_scores(self.golden_records, self.issues)
        print(f"      Global Executive Data Trust Index: {self.trust_scores['global_trust_score']}%")

        return {
            "golden_records": self.golden_records,
            "issues": self.issues,
            "trust_scores": self.trust_scores
        }

    def _data_reference_date(self):
        """The extract's own 'today': the latest plausible directory logon (extracts are snapshots)."""
        from datetime import datetime
        from src.ingestion.schema_mapper import parse_any_date
        latest = None
        now = datetime.now()
        for r in self.sources.get("access_directory", []):
            d = parse_any_date(r.get("last_logon_timestamp"))
            if d and d <= now and (latest is None or d > latest):
                latest = d
        return latest or now

    def export_submission_csv(self, output_path: str):
        """Exports the prioritized issue list to standardized CSV format."""
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        fieldnames = [
            "priority_rank",
            "issue_id",
            "severity",
            "category",
            "impact_score",
            "financial_risk_aed",
            "primary_entity_id",
            "entity_name",
            "source_systems",
            "fields_in_conflict",
            "description",
            "suggested_fix",
            "recommended_target_system",
            "recommended_target_field",
            "recommended_target_value",
            "confidence_score",
            "affected_reports",
            "downstream_impact",
            "evidence",
            "rationale",
            "approval_status"
        ]
        
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for rank, issue in enumerate(self.issues, 1):
                writer.writerow({
                    "priority_rank": rank,
                    "issue_id": issue.issue_id,
                    "severity": issue.severity.value,
                    "category": issue.category.value,
                    "impact_score": issue.impact_score,
                    "financial_risk_aed": issue.financial_risk_aed,
                    "primary_entity_id": issue.primary_entity_id,
                    "entity_name": issue.entity_name,
                    "source_systems": ";".join(issue.source_systems),
                    "fields_in_conflict": ";".join(issue.fields_in_conflict),
                    "description": issue.description,
                    "suggested_fix": issue.suggested_fix,
                    "recommended_target_system": issue.recommended_target_system,
                    "recommended_target_field": issue.recommended_target_field,
                    "recommended_target_value": str(issue.recommended_target_value),
                    "confidence_score": round(issue.confidence_score, 2),
                    "affected_reports": ";".join(issue.affected_reports),
                    "downstream_impact": " | ".join(n.name.replace("➔", "->") for n in issue.downstream_nodes),
                    "evidence": " | ".join(f"{e.system_name}.{e.field_name}={e.recorded_value}" + (" (system of record)" if e.is_authoritative else "")
                                           for e in issue.evidence_trail),
                    "rationale": issue.rationale,
                    "approval_status": issue.approval_status.value
                })
        print(f"Successfully exported {len(self.issues)} ranked issues to {output_path}")

    def evaluate_benchmark(self, ground_truth_path: str) -> Dict[str, Any]:
        """Evaluates detected issues against planted ground-truth errors."""
        if not os.path.exists(ground_truth_path):
            return {"status": "No ground truth file found."}

        with open(ground_truth_path, "r", encoding="utf-8") as f:
            ground_truth = json.load(f)

        gt_count = len(ground_truth)
        detected_count = len(self.issues)

        # Match by primary entity ID and category
        gt_keys = {(g["primary_entity_id"], g["category"]) for g in ground_truth}
        det_keys = {(i.primary_entity_id, i.category.value) for i in self.issues}

        true_positives = len(gt_keys.intersection(det_keys))
        false_positives = len(det_keys - gt_keys)
        false_negatives = len(gt_keys - det_keys)

        precision = true_positives / max(true_positives + false_positives, 1)
        recall = true_positives / max(true_positives + false_negatives, 1)
        f1 = (2 * precision * recall) / max(precision + recall, 1e-6)

        results = {
            "ground_truth_planted": gt_count,
            "detected_issues": detected_count,
            "true_positives": true_positives,
            "false_positives": false_positives,
            "false_negatives": false_negatives,
            "precision_rate": f"{precision * 100:.2f}%",
            "recall_rate": f"{recall * 100:.2f}%",
            "f1_accuracy_score": f"{f1 * 100:.2f}%"
        }
        return results

if __name__ == "__main__":
    import argparse
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ap = argparse.ArgumentParser(description="Run VeritasHR over a folder of HR source extracts.")
    ap.add_argument("--data", default=os.path.join(base_dir, "data", "raw"), help="Folder with the source files")
    ap.add_argument("--out", default=os.path.join(base_dir, "submission", "issue_list.csv"), help="Issue list CSV to write")
    ap.add_argument("--truth", default=os.path.join(base_dir, "data", "ground_truth_errors.json"), help="Answer key (optional)")
    args = ap.parse_args()
    raw_path, submission_path, gt_path = args.data, args.out, args.truth

    pipeline = VeritasHRPipeline(raw_path)
    pipeline.run()
    pipeline.export_submission_csv(submission_path)

    metrics = pipeline.evaluate_benchmark(gt_path)
    print("\n--- Accuracy Benchmark on Planted Errors ---")
    for k, v in metrics.items():
        print(f"  {k}: {v}")
