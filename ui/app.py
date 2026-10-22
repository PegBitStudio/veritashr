"""
VeritasHR: One Employee, One Truth - Executive Web Dashboard.
Built with Streamlit for Emirates Group HR Data Quality Challenge.
Features:
  - 3-Persona UX: HR Data Steward, HR Analytics Lead, HR Systems Owner
  - Real-time Entity Resolution & Anomaly Explorer
  - Human-in-the-Loop 1-Click Fix Approvals (Strictly no live auto-writebacks)
  - Downstream Blast-Radius Visualizer (Network DAG)
  - Executive Data-Trust Score Index
  - "Ask HR Truth" Natural Language Query Box
"""

import os
import sys
import json
import pandas as pd
import streamlit as st

# Add project root to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from src.pipeline import VeritasHRPipeline
from src.qa.query_box import AskHRTruthEngine
from src.governance.audit_log import AuditLog

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.environ.get("VERITAS_DATA_DIR", os.path.join(BASE_DIR, "data", "raw"))
AUDIT_PATH = os.environ.get("VERITAS_AUDIT_LOG", os.path.join(BASE_DIR, "audit", "decisions.jsonl"))

def mask(value, field):
    """Masks personal identifiers on screen unless the steward explicitly reveals them."""
    v = "" if value is None else str(value)
    if st.session_state.get("reveal_pii") or not v or v.startswith("["):
        return v
    if any(k in field for k in ("iban", "national_id", "passport")):
        return v[:4] + "•" * max(len(v) - 8, 3) + v[-4:] if len(v) > 8 else "•" * len(v)
    if "date_of_birth" in field:
        return v[:4] + "-••-••"
    return v

st.set_page_config(
    page_title="VeritasHR | One Employee, One Truth",
    page_icon="✈️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Emirates Aviation Inspired Styling
st.markdown("""
<style>
    .main-header {
        background: linear-gradient(135deg, #1A1A1A 0%, #2D0005 50%, #8A000A 100%);
        padding: 24px;
        border-radius: 12px;
        color: white;
        margin-bottom: 24px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
    }
    .main-header h1 {
        color: #FFFFFF !important;
        font-family: 'Inter', sans-serif;
        font-size: 2.2rem;
        margin: 0;
        font-weight: 700;
    }
    .main-header p {
        color: #E0E0E0 !important;
        font-size: 1.05rem;
        margin-top: 6px;
        margin-bottom: 0;
    }
    .kpi-card {
        background: #FFFFFF;
        border: 1px solid #EAEAEA;
        border-radius: 10px;
        padding: 16px;
        box-shadow: 0 2px 6px rgba(0,0,0,0.04);
        text-align: center;
    }
    .kpi-value {
        font-size: clamp(1.05rem, 1.9vw, 1.8rem);
        white-space: nowrap;
        font-weight: 700;
        color: #8A000A;
    }
    .kpi-label {
        font-size: clamp(0.6rem, 0.8vw, 0.85rem);
        color: #666;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    .badge-critical {
        background-color: #FFEBEB;
        color: #C00000;
        padding: 4px 8px;
        border-radius: 6px;
        font-weight: 600;
        font-size: 0.8rem;
    }
    .badge-high {
        background-color: #FFF4E5;
        color: #B25E00;
        padding: 4px 8px;
        border-radius: 6px;
        font-weight: 600;
        font-size: 0.8rem;
    }
    .badge-medium {
        background-color: #EBF5FF;
        color: #0066CC;
        padding: 4px 8px;
        border-radius: 6px;
        font-weight: 600;
        font-size: 0.8rem;
    }
</style>
""", unsafe_allow_html=True)

@st.cache_resource
def load_and_run_pipeline(data_dir):
    pipeline = VeritasHRPipeline(data_dir)
    res = pipeline.run()
    qa_engine = AskHRTruthEngine(res["golden_records"], res["issues"], pipeline.loader.catalog)
    return pipeline, res, qa_engine

pipeline, results, qa_engine = load_and_run_pipeline(DATA_DIR)
audit = AuditLog(AUDIT_PATH)
audit.apply_to_issues(results["issues"])

with st.sidebar:
    st.markdown("### 🛡️ Reviewer")
    reviewer = st.text_input("Your name / staff ID (recorded on every decision)", key="reviewer")
    st.toggle("Reveal personal identifiers (IBAN, Emirates ID, DOB)", key="reveal_pii", value=False)
    st.caption("Identifiers are masked by default. Data stays on this machine; nothing is sent to external AI services.")
    st.markdown("---")
    st.markdown("### 📂 Data source")
    st.caption(f"Folder: `{os.path.basename(os.path.normpath(DATA_DIR))}`")
    with st.expander("Column auto-mapping report"):
        for system, rep in pipeline.loader.mapper.report.items():
            st.markdown(f"**{system}** ← `{rep.get('file')}`")
            st.dataframe(pd.DataFrame([{"canonical field": c, "source column": m["source_column"], "method": m["method"]}
                                       for c, m in rep["mapped"].items()]), hide_index=True, width='stretch')
            if rep["missing_canonical_fields"]:
                st.caption("Not found: " + ", ".join(rep["missing_canonical_fields"]))
    st.caption(f"Lineage source: {pipeline.loader.dependencies.get('source', 'built-in')}")
issues = results["issues"]
trust_scores = results["trust_scores"]
golden_records = results["golden_records"]

# Header
st.markdown("""
<div class="main-header">
    <div style="display: flex; justify-content: space-between; align-items: center;">
        <div>
            <h1>✈️ VeritasHR: One Employee, One Truth</h1>
            <p>Emirates Group Intelligent HR Data Reconciliation, Anomaly Explanation & Blast-Radius Simulator</p>
        </div>
        <div style="text-align: right; background: rgba(255,255,255,0.1); padding: 10px 18px; border-radius: 8px;">
            <span style="font-size: 0.85rem; color: #FFD700; font-weight: 600;">PILOT-READY ARCHITECTURE</span><br/>
            <span style="font-size: 0.75rem; color: #FFF;">50+ HR Systems • Zero Live Writebacks</span>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

# Top KPI Row
k1, k2, k3, k4, k5 = st.columns(5)
with k1:
    st.markdown(f'<div class="kpi-card"><div class="kpi-value">{len(golden_records):,}</div><div class="kpi-label">Reconciled Profiles</div></div>', unsafe_allow_html=True)
with k2:
    st.markdown(f'<div class="kpi-card"><div class="kpi-value">{len(issues)}</div><div class="kpi-label">Issues Detected</div></div>', unsafe_allow_html=True)
with k3:
    crit_count = sum(1 for i in issues if i.severity == "CRITICAL")
    st.markdown(f'<div class="kpi-card"><div class="kpi-value" style="color: #C00000;">{crit_count}</div><div class="kpi-label">Critical Blocker Items</div></div>', unsafe_allow_html=True)
with k4:
    tot_cash_leakage = sum(i.financial_risk_aed for i in issues if i.financial_risk_aed > 0)
    st.markdown(f'<div class="kpi-card"><div class="kpi-value" style="color: #C00000;">AED {tot_cash_leakage/1e6:.1f}M</div><div class="kpi-label">Annual Pay Leakage Risk</div></div>', unsafe_allow_html=True)
with k5:
    g_score = trust_scores["global_trust_score"]
    st.markdown(f'<div class="kpi-card"><div class="kpi-value" style="color: #0288D1;">{g_score}%</div><div class="kpi-label">Global Trust Index</div></div>', unsafe_allow_html=True)

st.markdown("<br/>", unsafe_allow_html=True)

# Persona Selection Tabs
persona_tab1, persona_tab2, persona_tab3 = st.tabs([
    "🧑‍💼 HR Data Steward (Ranked Issues & Fix Approval)",
    "📊 HR Analytics Lead (Data Trust & Ask HR Truth)",
    "⚙️ HR Systems Owner (Blast Radius & Lineage)"
])

# -------------------------------------------------------------
# TAB 1: HR DATA STEWARD
# -------------------------------------------------------------
with persona_tab1:
    st.subheader("Prioritized Inconsistency Queue (Human-in-the-Loop)")
    st.caption("Review transparent root causes, inspect cross-system evidence, and approve or modify suggested fixes. No changes are written back automatically.")

    # Filter Controls
    f_col1, f_col2, f_col3 = st.columns([1, 1, 2])
    with f_col1:
        sev_filter = st.selectbox("Filter Severity:", ["ALL", "CRITICAL", "HIGH", "MEDIUM", "LOW"])
    with f_col2:
        cat_filter = st.selectbox("Filter Category:", ["ALL"] + sorted(list({i.category.value for i in issues})))
    with f_col3:
        search_query = st.text_input("Search Employee ID or Name:", "")

    filtered_issues = issues
    if sev_filter != "ALL":
        filtered_issues = [i for i in filtered_issues if i.severity.value == sev_filter]
    if cat_filter != "ALL":
        filtered_issues = [i for i in filtered_issues if i.category.value == cat_filter]
    if search_query:
        sq = search_query.lower()
        filtered_issues = [i for i in filtered_issues if sq in i.primary_entity_id.lower() or sq in i.entity_name.lower()]

    st.write(f"Showing **{len(filtered_issues)}** prioritized issues:")

    # Issue Table
    table_data = []
    for rank, issue in enumerate(filtered_issues[:50], 1):
        table_data.append({
            "Rank": rank,
            "Issue ID": issue.issue_id,
            "Severity": issue.severity.value,
            "Category": issue.category.value,
            "Entity": f"{issue.entity_name} ({issue.primary_entity_id})",
            "Impact Score": f"{issue.impact_score:.1f}",
            "Financial Risk": f"AED {issue.financial_risk_aed:,.0f}" if issue.financial_risk_aed > 0 else "-",
            "Suggested Action": issue.suggested_fix,
            "Status": issue.approval_status.value
        })
    df_table = pd.DataFrame(table_data)
    st.dataframe(df_table, width='stretch', height=280, hide_index=True)

    # Detailed Inspection Card
    st.markdown("---")
    st.subheader("🔍 Issue Evidence & Fix Approval Inspection")
    
    selected_issue_id = st.selectbox(
        "Select Issue to Inspect:",
        [i.issue_id for i in filtered_issues[:50]],
        format_func=lambda x: f"{x} - {next((i.title for i in issues if i.issue_id == x), '')}"
    )

    if selected_issue_id:
        target_issue = next(i for i in issues if i.issue_id == selected_issue_id)
        
        c_left, c_right = st.columns([3, 2])
        
        with c_left:
            st.markdown(f"### {target_issue.title}")
            st.write(f"**Entity:** {target_issue.entity_name} | **Primary ID:** `{target_issue.primary_entity_id}`")
            st.info(f"**Plain-Language Explanation:**\n\n{target_issue.description}")
            
            st.markdown("#### 📑 Cross-System Evidence Trail")
            ev_data = []
            for ev in target_issue.evidence_trail:
                ev_data.append({
                    "System": ev.system_name.upper(),
                    "Field": ev.field_name,
                    "Recorded Value": mask(ev.recorded_value, ev.field_name),
                    "Authoritative?": "⭐️ YES (System of Record)" if ev.is_authoritative else "Secondary Feed"
                })
            st.table(pd.DataFrame(ev_data))

        with c_right:
            st.markdown("### 💡 Recommended Fix")
            st.success(f"**Suggested Action:**\n\n{target_issue.suggested_fix}")
            st.write(f"**Target System:** `{target_issue.recommended_target_system}`")
            st.write(f"**Target Field:** `{target_issue.recommended_target_field}`")
            st.write(f"**Recommended Value:** `{target_issue.recommended_target_value}`")
            st.write(f"**AI Confidence:** `{target_issue.confidence_score * 100:.0f}%`")
            st.caption(f"**Logic / Precedence Rationale:** {target_issue.rationale}")
            
            st.markdown("---")
            st.markdown("#### 🛡️ Human Approval Action")
            st.caption(f"Current status: **{target_issue.approval_status.value}**"
                       + (f" by {target_issue.approved_by} at {target_issue.reviewed_at}" if target_issue.approved_by else ""))
            if target_issue.downstream_nodes:
                st.caption("Approving will affect: " + ", ".join(n.name for n in target_issue.downstream_nodes))
            new_value = st.text_input("Replacement value (for Modify)", value=str(target_issue.recommended_target_value),
                                      key=f"val_{target_issue.issue_id}")
            comment = st.text_input("Comment / reason (required to Reject)", key=f"cmt_{target_issue.issue_id}")
            app_col1, app_col2, app_col3 = st.columns(3)
            decision = None
            with app_col1:
                if st.button("✅ Approve Fix", key=f"app_{target_issue.issue_id}"):
                    decision = ("APPROVE", None)
            with app_col2:
                if st.button("✏️ Modify", key=f"mod_{target_issue.issue_id}"):
                    decision = ("MODIFY", new_value)
            with app_col3:
                if st.button("❌ Reject", key=f"rej_{target_issue.issue_id}"):
                    decision = ("REJECT", None)
            if decision:
                try:
                    entry = audit.record(target_issue, decision[0], reviewer, comment, final_value=decision[1])
                    st.success(f"{entry['action']} recorded for {entry['reviewer']} (audit #{entry['seq']}, hash {entry['hash'][:12]}…). "
                               "Nothing has been written to any HR system.")
                except ValueError as e:
                    st.error(str(e))

    # Audit trail
    st.markdown("---")
    st.subheader("📜 Decision Audit Trail")
    entries = audit.entries()
    ok, msg = audit.verify()
    (st.success if ok else st.error)(("🔒 " if ok else "⚠️ ") + msg)
    if entries:
        st.dataframe(pd.DataFrame([{k: e[k] for k in ("seq", "timestamp_utc", "reviewer", "action", "issue_id", "target",
                                                       "current_value", "final_value", "comment")} for e in entries][::-1]),
                     hide_index=True, width='stretch', height=220)
        change_path = os.path.join(BASE_DIR, "audit", "approved_change_set.csv")
        n = audit.export_change_set(change_path)
        with open(change_path, "rb") as f:
            st.download_button(f"📤 Download approved change set ({n} fixes) for the system owner", f,
                               file_name="approved_change_set.csv", mime="text/csv")
    else:
        st.caption("No decisions yet. Every approval, modification and rejection will appear here with reviewer, time and a hash chain.")

    # Export Button for Test Set Submission
    st.markdown("---")
    csv_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "submission", "issue_list.csv")
    if os.path.exists(csv_path):
        with open(csv_path, "rb") as f:
            st.download_button(
                label="📥 Download Official Ranked Issue List (submission/issue_list.csv)",
                data=f,
                file_name="issue_list_submission.csv",
                mime="text/csv",
                width='stretch'
            )

# -------------------------------------------------------------
# TAB 2: HR ANALYTICS LEAD
# -------------------------------------------------------------
with persona_tab2:
    st.subheader("Executive Data-Trust & Reporting Reliability Index")
    st.caption("Know which numbers can be trusted for C-suite executive boards and statutory regulatory filings.")

    col_reports, col_qa = st.columns([1, 1])

    with col_reports:
        st.markdown("### 📋 Executive & Statutory Reports Trust Index")
        st.caption("Trust = share of employee records whose fields used by the report have no open issue. "
                   "A report is not safe to file while any CRITICAL issue touches it.")
        rep_scores = trust_scores["report_trust_scores"]
        for rep_id, rep_info in rep_scores.items():
            sc = rep_info["trust_score"]
            status_icon = {"HEALTHY": "🟢", "WATCH": "🟡", "AT RISK": "🔴"}[rep_info["status"]]
            with st.expander(f"{status_icon} **{rep_id}**: {rep_info['name']} ({sc}% trust, {rep_info['status']})",
                             expanded=not rep_info["certifiable"]):
                st.write(f"**Owner:** {rep_info['owner']}")
                st.progress(sc / 100.0)
                if not rep_info["certifiable"]:
                    st.error(f"Not safe to file: {rep_info['critical_issues']} critical issue(s) open.")
                st.write(f"**Records affected:** {rep_info['records_affected']:,} | **Open issues:** {rep_info['blocking_issues_count']}")
                st.dataframe(pd.DataFrame([{"Field used by report": f, "Field trust (%)": v} for f, v in rep_info["field_scores"].items()]),
                             hide_index=True, width='stretch')
                if rep_info["primary_risks"]:
                    st.write("**Main causes:** " + "; ".join(rep_info["primary_risks"]))

        st.markdown("### 🗄️ System-Level Integrity")
        sys_scores = trust_scores["system_trust_scores"]
        st.dataframe(pd.DataFrame(list(sys_scores.items()), columns=["System", "Records with no open issue (%)"]), hide_index=True)

    with col_qa:
        st.markdown("### 💬 'Ask HR Truth' Natural Language Query Box")
        st.caption("Ask high-level workforce questions. VeritasHR synthesizes the authoritative answer, cites the underlying system of record, and highlights active data quality risks.")
        
        sample_q = st.radio(
            "Quick Suggestions:",
            [
                "How many active employees in Dubai?",
                "What is our financial exposure to ghost payroll?",
                "How many active flight crew and pilots?",
                "Total monthly salary for cabin crew",
                "How many Emirati employees in grade G05?",
                "How many pilots have expired training?",
                "How many leavers still have system access?",
                "Custom Query..."
            ]
        )
        
        user_q = sample_q
        if sample_q == "Custom Query...":
            user_q = st.text_input("Enter your HR inquiry:", "How many active employees across Emirates Group?")
            
        if user_q:
            ans = qa_engine.answer_query(user_q)
            st.markdown(f"#### 💡 Result: **{ans['headline_answer']}**")
            st.caption(f"Interpreted as: {ans.get('interpretation', '')}")
            
            st.markdown(f"**Authoritative Source Relied On:**\n\n📌 `{ans['authoritative_source']}`")
            st.markdown(f"**Confidence Level:** `{ans['trust_confidence']}`")
            
            st.warning(f"**Executive Reliability Caveat:**\n\n{ans['quality_caveat']}")
            
            st.markdown("**Metric Breakdown:**")
            st.json(ans["breakdown"])

# -------------------------------------------------------------
# TAB 3: HR SYSTEMS OWNER
# -------------------------------------------------------------
with persona_tab3:
    st.subheader("Downstream Dependency & Blast Radius Simulation")
    st.caption("Simulate the exact ripple effect of a data fix across 50+ integrations, downstream feeds, and executive reports BEFORE approving the change.")

    sim_issue_id = st.selectbox(
        "Select Proposed Fix to Simulate Blast Radius:",
        [i.issue_id for i in issues[:30]],
        key="sim_select"
    )

    if sim_issue_id:
        sim_issue = next(i for i in issues if i.issue_id == sim_issue_id)
        
        st.markdown(f"### Proposed Fix: **{sim_issue.suggested_fix}**")
        st.write(f"Targeting `{sim_issue.recommended_target_system}.{sim_issue.recommended_target_field}` ➔ `{sim_issue.recommended_target_value}`")
        
        downstream_nodes = sim_issue.downstream_nodes
        feeds = [n for n in downstream_nodes if n.node_type == "SYSTEM_FEED"]
        reps = [n for n in downstream_nodes if n.node_type == "EXECUTIVE_REPORT"]
        current = next((ev.recorded_value for ev in sim_issue.evidence_trail
                        if ev.system_name == sim_issue.recommended_target_system and ev.field_name == sim_issue.recommended_target_field), None)

        # Impact graph: the change, the feeds that carry it, and the reports that read it
        def q(t):
            return '"' + str(t).replace('"', "'") + '"'
        target = f"{sim_issue.recommended_target_system}.{sim_issue.recommended_target_field}"
        shown_now = mask(current, target) if current is not None else "?"
        change = f"{target}\\n{shown_now}  ->  {sim_issue.recommended_target_value}"
        dot = ['digraph G { rankdir=LR; bgcolor="transparent"; node [shape=box, style="rounded,filled", fontname="Helvetica", fontsize=16, margin="0.25,0.15"]; ranksep=1.0; nodesep=0.4; edge [color="#888888"];',
               f'chg [label={q("Proposed fix (needs approval)" + chr(92) + "n" + change)}, fillcolor="#FDECEC", color="#C8102E", penwidth=2];']
        for k, f in enumerate(feeds):
            dot.append(f'f{k} [label={q(f.name.replace(" ➔ ", " -> "))}, fillcolor="#F5F5F7", color="#999999"]; chg -> f{k};')
        for k, r in enumerate(reps):
            dot.append(f'r{k} [label={q(r.name)}, fillcolor="#EAF4EC", color="#2E7D32"];')
            dot.append(f"chg -> r{k};")
        dot.append("}")
        st.graphviz_chart("\n".join(dot), width='stretch')

        b1, b2 = st.columns([1, 1])
        with b1:
            st.markdown("#### ⚡ Feeds that carry this change")
            if feeds:
                for f in feeds:
                    st.markdown(f"- **{f.name}**: {f.impact_description}")
            else:
                st.info("No batch feeds affected. The change stays in this system.")
        with b2:
            st.markdown("#### 📑 Reports that read this field")
            if reps:
                for r in reps:
                    st.markdown(f"- **{r.name}**: {r.impact_description.rstrip('.')}.")
            else:
                st.info("No executive or regulatory reports read this field.")

        st.markdown("---")
        st.markdown("#### 🔄 Before vs. after (preview only)")
        diff_col1, diff_col2 = st.columns(2)
        with diff_col1:
            st.markdown("**Today:**")
            now_value = mask(current, target) if current is not None else "(see evidence)"
            st.code(f"System: {sim_issue.recommended_target_system}\nField:  {sim_issue.recommended_target_field}\nValue:  {now_value}", language="yaml")
        with diff_col2:
            st.markdown("**After the fix is approved and applied:**")
            st.code(f"System: {sim_issue.recommended_target_system}\nField:  {sim_issue.recommended_target_field}\nValue:  {sim_issue.recommended_target_value}\n"
                    f"Status: {sim_issue.approval_status.value} (applied by the system owner, never automatically)", language="yaml")

st.markdown("---")
st.markdown("<div style='text-align: center; color: #888; font-size: 0.8rem;'>VeritasHR | Developed for Emirates Group HR Data Quality Challenge | Ignyte Competition</div>", unsafe_allow_html=True)
