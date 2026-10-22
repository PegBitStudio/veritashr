"""
Downstream Dependency DAG and Blast Radius Simulator for VeritasHR.
Traverses system and report lineage graphs to compute the ripple effect of any proposed data fix.
"""

from typing import Dict, List, Set, Any
from src.models.issue import BlastRadiusNode, QualityIssue

class BlastRadiusSimulator:
    def __init__(self, dependencies: Dict[str, Any]):
        self.dependencies = dependencies
        self.reports = dependencies.get("reports", {})
        self.feeds = dependencies.get("feeds", [])

    def simulate_impact(self, issue: QualityIssue) -> List[BlastRadiusNode]:
        """
        Simulates the downstream blast radius for a given issue and proposed fix.
        Identifies which systems and executive reports are touched.
        """
        nodes: List[BlastRadiusNode] = []
        target_sys = issue.recommended_target_system
        target_field = issue.recommended_target_field
        
        # 1. System Integrations Touched
        if target_sys == "core_hr":
            if "status" in target_field or "termination" in target_field:
                nodes.append(BlastRadiusNode(
                    node_id="feed-core-to-payroll",
                    node_type="SYSTEM_FEED",
                    name="Core HR ➔ Payroll Sync Feed",
                    impact_description="Synchronizes employee termination status; halts next month's salary accrual."
                ))
                nodes.append(BlastRadiusNode(
                    node_id="feed-core-to-ad",
                    node_type="SYSTEM_FEED",
                    name="Core HR ➔ IAM Deprovisioning Feed",
                    impact_description="Queues automated AD account deactivation and badge access revocation."
                ))
            elif "dept" in target_field:
                nodes.append(BlastRadiusNode(
                    node_id="feed-core-to-lms",
                    node_type="SYSTEM_FEED",
                    name="Core HR ➔ LMS Role Mapping Feed",
                    impact_description="Re-evaluates role-based safety curriculum assignments."
                ))

        elif target_sys == "payroll":
            if "pay_status" in target_field or "salary" in target_field or "iban" in target_field:
                nodes.append(BlastRadiusNode(
                    node_id="feed-payroll-to-wps",
                    node_type="SYSTEM_FEED",
                    name="Payroll ➔ UAE Central Bank WPS Feed",
                    impact_description="Recalculates monthly disbursement file before the 25th payroll cutoff."
                ))

        elif target_sys == "access_directory":
            nodes.append(BlastRadiusNode(
                node_id="feed-ad-to-perimeter",
                node_type="SYSTEM_FEED",
                name="Active Directory ➔ SSO / Physical Airside Access",
                impact_description="Revokes corporate VPN tokens and airport badge access."
            ))

        # 1b. Lineage-derived feeds: every system/report downstream of the system being changed (from dependencies.md)
        seen_feeds = {n.node_id for n in nodes}
        frontier, visited = [target_sys], {target_sys}
        while frontier:
            cur = frontier.pop()
            for src, dst, label in self.feeds:
                if src != cur or dst in visited:
                    continue
                visited.add(dst)
                frontier.append(dst)
                nid = f"lineage-{src}-{dst}"
                already_shown = any(dst.lower().replace("_", " ") in n.name.lower() for n in nodes)
                if nid not in seen_feeds and not dst.startswith("REP-") and not already_shown:
                    seen_feeds.add(nid)
                    nodes.append(BlastRadiusNode(
                        node_id=nid, node_type="SYSTEM_FEED",
                        name=f"{src} ➔ {dst}" + (f" ({label})" if label else ""),
                        impact_description=f"Change propagates from {src} to {dst} on the next sync."))

        # Reports that read the field this fix changes, according to the lineage file
        touched = {f"{target_sys}.{target_field}"}
        for rid, meta in self.reports.items():
            if rid not in issue.affected_reports and touched & set(meta.get("fields", [])):
                issue.affected_reports.append(rid)

        # 2. Executive & Regulatory Reports Touched
        for rep_id in issue.affected_reports:
            rep_meta = self.reports.get(rep_id, {})
            nodes.append(BlastRadiusNode(
                node_id=rep_id,
                node_type="EXECUTIVE_REPORT",
                name=rep_meta.get("name", rep_id),
                impact_description=f"Reads this field. Risk while unfixed: {rep_meta.get('impact', 'reporting distortion').rstrip('.')}."
            ))

        issue.downstream_nodes = nodes
        return nodes
