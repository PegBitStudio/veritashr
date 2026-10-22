"""
Builds an executive, visual, award-winning 2-page Solution Note PDF for VeritasHR.
Uses modern card layouts, KPI grids, visual chevrons, and UI screenshots.
Strictly calibrated for an exact 2-page A4 printout.
"""

import os
import fitz # PyMuPDF
from playwright.sync_api import sync_playwright

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, "docs", "solution_note.pdf")
EVIDENCE_IMG = os.path.join(BASE, "docs", "img", "evidence.png").replace(os.sep, "/")
IMPACT_IMG = os.path.join(BASE, "docs", "img", "impact.png").replace(os.sep, "/")

HTML_CONTENT = f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<style>
  @page {{
    size: A4 portrait;
    margin: 10mm 12mm 10mm 12mm;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
    font-size: 8.2pt;
    line-height: 1.32;
    color: #1F2937;
    margin: 0;
    padding: 0;
  }}

  /* Page Break Control */
  .page {{
    height: 275mm;
    max-height: 275mm;
    overflow: hidden;
    position: relative;
    page-break-after: always;
  }}
  .page:last-child {{
    page-break-after: avoid;
  }}

  /* Header Banner */
  .header-banner {{
    background: linear-gradient(135deg, #111827 0%, #3B0008 50%, #8A000A 100%);
    color: #FFFFFF;
    padding: 10px 14px;
    border-radius: 6px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 8px;
  }}
  .header-banner h1 {{
    margin: 0;
    font-size: 15pt;
    font-weight: 700;
    letter-spacing: -0.2px;
  }}
  .header-banner p {{
    margin: 2px 0 0;
    font-size: 8.5pt;
    color: #E5E7EB;
  }}
  .header-links {{
    text-align: right;
    font-size: 7.8pt;
  }}
  .badge-link {{
    display: inline-block;
    background: rgba(255, 255, 255, 0.15);
    border: 1px solid rgba(255, 215, 0, 0.6);
    color: #FFD700 !important;
    text-decoration: none;
    font-weight: 600;
    padding: 3px 7px;
    border-radius: 4px;
    margin-left: 4px;
  }}

  /* 4 Hero KPI Cards */
  .kpi-grid {{
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 6px;
    margin-bottom: 8px;
  }}
  .kpi-card {{
    background: #F9FAFB;
    border: 1px solid #E5E7EB;
    border-top: 3px solid #8A000A;
    border-radius: 6px;
    padding: 6px 8px;
    text-align: center;
  }}
  .kpi-val {{
    font-size: 13.5pt;
    font-weight: 800;
    color: #8A000A;
    line-height: 1.1;
  }}
  .kpi-lbl {{
    font-size: 6.8pt;
    font-weight: 700;
    color: #4B5563;
    text-transform: uppercase;
    letter-spacing: 0.3px;
    margin-top: 2px;
  }}
  .kpi-sub {{
    font-size: 6.8pt;
    color: #6B7280;
  }}

  /* Section Titles */
  .section-title {{
    font-size: 9.8pt;
    font-weight: 700;
    color: #8A000A;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    border-bottom: 1.5px solid #F3C5C9;
    padding-bottom: 2px;
    margin: 6px 0 5px;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }}

  /* 3 Persona Cards */
  .persona-grid {{
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 6px;
    margin-bottom: 7px;
  }}
  .persona-card {{
    background: #FFFFFF;
    border: 1px solid #E5E7EB;
    border-radius: 6px;
    padding: 7px 8px;
  }}
  .persona-card.steward {{ border-left: 3.5px solid #8A000A; }}
  .persona-card.analytics {{ border-left: 3.5px solid #2563EB; }}
  .persona-card.systems {{ border-left: 3.5px solid #059669; }}
  .persona-head {{
    font-weight: 700;
    font-size: 8.5pt;
    margin-bottom: 3px;
    display: flex;
    align-items: center;
    gap: 4px;
  }}
  .persona-head.steward {{ color: #8A000A; }}
  .persona-head.analytics {{ color: #2563EB; }}
  .persona-head.systems {{ color: #059669; }}
  .persona-card ul {{
    margin: 0;
    padding-left: 12px;
    font-size: 7.6pt;
    color: #374151;
  }}
  .persona-card li {{ margin-bottom: 2px; }}

  /* Process Flow Chevron Bar */
  .process-bar {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    background: #FDF2F2;
    border: 1px solid #FCA5A5;
    border-radius: 5px;
    padding: 4px 8px;
    margin-bottom: 7px;
    font-size: 7.4pt;
    font-weight: 600;
  }}
  .step-node {{
    display: flex;
    align-items: center;
    gap: 3px;
    color: #991B1B;
  }}
  .step-arrow {{
    color: #DC2626;
    font-size: 8pt;
    font-weight: 700;
  }}

  /* Two Column Detail Block */
  .two-col {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
  }}
  .detail-box {{
    background: #F9FAFB;
    border: 1px solid #E5E7EB;
    border-radius: 5px;
    padding: 6px 8px;
  }}
  .detail-box h4 {{
    margin: 0 0 3px;
    font-size: 8.2pt;
    color: #111827;
  }}
  .detail-box p {{
    margin: 0;
    font-size: 7.6pt;
    color: #4B5563;
  }}

  /* Tables */
  table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 7.6pt;
    margin: 4px 0 6px;
  }}
  th {{
    background: #F3F4F6;
    color: #374151;
    font-weight: 700;
    text-align: left;
    padding: 4px 6px;
    border: 1px solid #E5E7EB;
  }}
  td {{
    padding: 3px 6px;
    border: 1px solid #E5E7EB;
    color: #1F2937;
  }}
  .tag-pass {{
    background: #DEF7EC;
    color: #03543F;
    font-weight: 700;
    padding: 1px 5px;
    border-radius: 3px;
    font-size: 7pt;
  }}

  /* Visual Screenshots Grid */
  .shots-grid {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
    margin: 5px 0 7px;
  }}
  .shot-card {{
    border: 1px solid #D1D5DB;
    border-radius: 6px;
    padding: 4px;
    background: #FFFFFF;
    text-align: center;
  }}
  .shot-card img {{
    width: 100%;
    height: 125px;
    object-fit: cover;
    object-position: top;
    border-radius: 4px;
    border: 1px solid #E5E7EB;
    display: block;
  }}
  .shot-cap {{
    font-size: 7.2pt;
    color: #4B5563;
    font-weight: 600;
    margin-top: 3px;
  }}

  /* Governance Shield Box */
  .gov-grid {{
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 6px;
    margin-bottom: 7px;
  }}
  .gov-card {{
    background: #F0FDF4;
    border: 1px solid #BBF7D0;
    border-radius: 5px;
    padding: 5px 6px;
    font-size: 7.2pt;
  }}
  .gov-title {{
    font-weight: 700;
    color: #166534;
    font-size: 7.6pt;
    margin-bottom: 2px;
  }}

  /* Timeline */
  .pilot-timeline {{
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 6px;
  }}
  .pilot-step {{
    background: #EFF6FF;
    border: 1px solid #BFDBFE;
    border-radius: 5px;
    padding: 5px 7px;
  }}
  .pilot-step h5 {{
    margin: 0 0 2px;
    font-size: 7.6pt;
    color: #1E40AF;
  }}
  .pilot-step p {{
    margin: 0;
    font-size: 7.2pt;
    color: #1E3A8A;
  }}

  .footer-note {{
    position: absolute;
    bottom: 0;
    left: 0;
    right: 0;
    font-size: 6.8pt;
    color: #9CA3AF;
    display: flex;
    justify-content: space-between;
    border-top: 1px solid #E5E7EB;
    padding-top: 3px;
  }}
</style>
</head>
<body>

<!-- ================= PAGE 1 ================= -->
<div class="page">
  <!-- Top Banner -->
  <div class="header-banner">
    <div>
      <h1>✈️ VeritasHR: One Employee, One Truth</h1>
      <p>Emirates Group HR Data Quality Challenge | Ignyte Competition Brief</p>
    </div>
    <div class="header-links">
      <a class="badge-link" href="https://github.com/PegBitStudio/veritashr">🔗 GitHub Code</a>
      <a class="badge-link" href="https://github.com/PegBitStudio/veritashr/blob/main/docs/demo_video.mp4">🎥 Demo Video (2m49s)</a>
      <a class="badge-link" href="https://github.com/PegBitStudio/veritashr/blob/main/submission/issue_list.csv">📊 Issue List (CSV)</a>
    </div>
  </div>

  <!-- 4 Hero KPI Cards -->
  <div class="kpi-grid">
    <div class="kpi-card">
      <div class="kpi-val">99.8%</div>
      <div class="kpi-lbl">F1 Accuracy</div>
      <div class="kpi-sub">255/255 Planted Errors (100% Recall)</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-val">AED 18.2M</div>
      <div class="kpi-lbl">Cash Leakage Identified</div>
      <div class="kpi-sub">35 Ghost Payroll Cases Halted</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-val">100%</div>
      <div class="kpi-lbl">Human-in-the-Loop</div>
      <div class="kpi-sub">Tamper-Evident SHA-256 Audit Trail</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-val">&lt; 4.4s</div>
      <div class="kpi-lbl">Full Run Latency</div>
      <div class="kpi-sub">20,030 Records Reconciled Locally</div>
    </div>
  </div>

  <!-- 1. The 3 Target Personas -->
  <div class="section-title">
    <span>1. Who We Built For (The 3 Personas)</span>
    <span style="font-size: 7.2pt; font-weight: normal; color: #6B7280;">Single Source of Truth</span>
  </div>
  <div class="persona-grid">
    <div class="persona-card steward">
      <div class="persona-head steward">🧑‍💼 HR Data Steward</div>
      <ul>
        <li><b>Ranked Issue Queue</b> prioritized by financial cash leakage, security exposure & statutory risk.</li>
        <li><b>Side-by-Side Evidence Cards</b> showing conflicting timestamps across Core HR, Payroll, LMS & AD.</li>
        <li><b>1-Click Human Actions</b>: Approve, Modify or Reject with mandatory reviewer reason.</li>
      </ul>
    </div>
    <div class="persona-card analytics">
      <div class="persona-head analytics">📊 HR Analytics Lead</div>
      <ul>
        <li><b>Data-Trust Index (0–100%)</b> per report & field; flags when reports are <i>"Safe to File"</i>.</li>
        <li><b>"Ask HR Truth" Query Box</b>: plain-language question tool citing authoritative System of Record.</li>
        <li><b>Active Anomaly Warnings</b>: alerts executives if data discrepancies skew headline headcount.</li>
      </ul>
    </div>
    <div class="persona-card systems">
      <div class="persona-head systems">⚙️ HR Systems Owner</div>
      <ul>
        <li><b>Blast-Radius Simulator</b>: walks <code>dependencies.md</code> DAG before any fix is committed.</li>
        <li><b>Downstream Feed Previews</b>: shows impacts on WPS Payroll, GCAA Aviation Safety & AD.</li>
        <li><b>Before-vs-After Diffs</b>: staged changes exportable for standard change-advisory boards.</li>
      </ul>
    </div>
  </div>

  <!-- 2. The 6-Step Visual Process Flow -->
  <div class="section-title">
    <span>2. How It Works (End-to-End Pipeline)</span>
    <span style="font-size: 7.2pt; font-weight: normal; color: #6B7280;">Fully Automated &amp; Offline</span>
  </div>
  <div class="process-bar">
    <div class="step-node"><span>1. Ingest Any Layout</span></div>
    <div class="step-arrow">➔</div>
    <div class="step-node"><span>2. Match People</span></div>
    <div class="step-arrow">➔</div>
    <div class="step-node"><span>3. Detect 10 Families</span></div>
    <div class="step-arrow">➔</div>
    <div class="step-node"><span>4. Simulate Blast Radius</span></div>
    <div class="step-arrow">➔</div>
    <div class="step-node"><span>5. Human Approval</span></div>
    <div class="step-arrow">➔</div>
    <div class="step-node"><span>6. Cryptographic Audit</span></div>
  </div>

  <!-- Ingestion & Matching Architecture Details -->
  <div class="two-col">
    <div class="detail-box">
      <h4>📂 Universal Ingestion &amp; Schema Sniffing</h4>
      <p>Accepts extracts in any delimiter (<code>,</code>, <code>;</code>, <code>\t</code>), encoding, Excel, or JSON. Columns are mapped automatically via header aliases (e.g. <i>Staff No</i> ➔ <code>employee_id</code>) and content sniffing (recognizing <code>AE...</code> as IBANs). Custom overrides can be pinned in <code>schema_mapping.json</code>. Dynamic parsers read reference codes from <code>data_dictionary.md</code> and lineage DAGs from <code>dependencies.md</code>.</p>
    </div>
    <div class="detail-box">
      <h4>🔗 Two-Pass Entity Resolution &amp; Disambiguation</h4>
      <p><b>Pass 1:</b> Deterministic matching on normalized &amp; numeric IDs (<code>EK10001</code> = <code>ek-10001</code> = <code>10001</code>).<br/>
      <b>Pass 2:</b> Jaro-Winkler fuzzy name matching for missing IDs, with Date of Birth blocking &amp; attribute corroboration (hire date, department, role). Prevents accidental collision between distinct staff sharing the same name.</p>
    </div>
  </div>

  <!-- 10 Issue Families Checked -->
  <div class="section-title" style="margin-top: 7px;">
    <span>3. Comprehensive Inconsistency Detection (10 Issue Families)</span>
  </div>
  <table style="margin: 0;">
    <thead>
      <tr>
        <th style="width: 28%;">Issue Family</th>
        <th style="width: 44%;">Detection Logic &amp; Real-World Example</th>
        <th style="width: 28%;">Downstream Business Impact</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td><b>Ghost Payroll</b></td>
        <td>Terminated in Core HR, but still active in Payroll receiving salary.</td>
        <td>Direct cash leakage (AED 816k/yr in single pilot case).</td>
      </tr>
      <tr>
        <td><b>Zombie IT Accounts</b></td>
        <td>Ex-employee retaining active AD account with post-exit logins.</td>
        <td>Severe cyber vulnerability &amp; ISO 27001 audit citation.</td>
      </tr>
      <tr>
        <td><b>Double Dipping</b></td>
        <td>Single employee linked to multiple active payroll disbursement IDs.</td>
        <td>Duplicate salary payments &amp; inflated headcount.</td>
      </tr>
      <tr>
        <td><b>Department &amp; Cost Drift</b></td>
        <td>Core HR department assignment differs from Payroll cost center or LMS.</td>
        <td>Cross-charging misallocations &amp; skewed training budgets.</td>
      </tr>
      <tr>
        <td><b>Regulatory Deficits</b></td>
        <td>Active flight crew/pilots with expired GCAA safety certifications.</td>
        <td>Aircraft groundings, pilot rostering blocks &amp; GCAA fines.</td>
      </tr>
      <tr>
        <td><b>Temporal Paradoxes</b></td>
        <td>Termination date preceding hire date; hire date in the future.</td>
        <td>ETL warehouse ingestion crashes &amp; inaccurate seniority.</td>
      </tr>
    </tbody>
  </table>

  <div class="footer-note">
    <span>VeritasHR: Solution Note | Page 1 of 2</span>
    <span>Emirates Group HR Data Quality Challenge (Ignyte)</span>
    <span>Confidential - For Competition Evaluation Only</span>
  </div>
</div>

<!-- ================= PAGE 2 ================= -->
<div class="page">
  <!-- Visual UI Proofs -->
  <div class="section-title" style="margin-top: 0;">
    <span>4. What It Looks Like in Practice (Verified Prototype)</span>
    <span style="font-size: 7.2pt; font-weight: normal; color: #6B7280;">Live Web Dashboard</span>
  </div>
  <div class="shots-grid">
    <div class="shot-card">
      <img src="{EVIDENCE_IMG}" alt="Evidence Card">
      <div class="shot-cap">🔍 Side-by-Side Evidence Inspection (Core HR marked as System of Record)</div>
    </div>
    <div class="shot-card">
      <img src="{IMPACT_IMG}" alt="Blast Radius DAG">
      <div class="shot-cap">⚡ Downstream Blast Radius: Feeds &amp; Reports Touched Before Approval</div>
    </div>
  </div>

  <!-- Benchmark Proofs Table -->
  <div class="section-title">
    <span>5. Benchmark Accuracy &amp; Robustness Proofs (34 Automated Tests)</span>
  </div>
  <table>
    <thead>
      <tr>
        <th style="width: 24%;">Evaluation Suite</th>
        <th style="width: 48%;">Dataset Configuration &amp; Stress Condition</th>
        <th style="width: 14%;">Latency</th>
        <th style="width: 14%;">Accuracy Result</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td><b>Synthetic Benchmark</b></td>
        <td>20,030 records across 4 systems; 255 planted errors across all categories.</td>
        <td>4.40s</td>
        <td><span class="tag-pass">255/255 (F1 99.8%)</span></td>
      </tr>
      <tr>
        <td><b>Scrambled Variant</b></td>
        <td>Renamed columns, semicolon delimiters (<code>;</code>), 12+ date formats, 10% IDs stripped.</td>
        <td>4.10s</td>
        <td><span class="tag-pass">100% Mapped (F1 99.8%)</span></td>
      </tr>
      <tr>
        <td><b>Blind Error Test</b></td>
        <td>80 unseen errors across 10 novel edge cases not in training scripts.</td>
        <td>3.80s</td>
        <td><span class="tag-pass">80/80 Detected</span></td>
      </tr>
      <tr>
        <td><b>5th Unseen System</b></td>
        <td>Time-attendance file dropped into folder; auto-mapped and linked dynamically.</td>
        <td>1.10s</td>
        <td><span class="tag-pass">13/13 (0 False Alarms)</span></td>
      </tr>
    </tbody>
  </table>

  <!-- Responsible AI & Data Security Shield -->
  <div class="section-title">
    <span>6. Responsible AI, Security &amp; UAE Compliance</span>
    <span style="font-size: 7.2pt; font-weight: normal; color: #6B7280;">Strict Ethical Guardrails</span>
  </div>
  <div class="gov-grid">
    <div class="gov-card">
      <div class="gov-title">🛡️ Human-in-the-Loop</div>
      Zero live database writebacks. All fixes are suggested proposals requiring named steward sign-off.
    </div>
    <div class="gov-card">
      <div class="gov-title">⛓️ Tamper-Evident Audit</div>
      Decisions recorded in an append-only log with SHA-256 hash chaining. Any tampering breaks verification.
    </div>
    <div class="gov-card">
      <div class="gov-title">🔒 UAE PDPL Aligned</div>
      Runs 100% offline. Zero external API calls. Personal identifiers (IBAN, EID, DOB) masked by default.
    </div>
    <div class="gov-card">
      <div class="gov-title">💡 Deterministic XAI</div>
      No black-box hallucination. Every suggestion provides confidence scores, source rules &amp; rationale.
    </div>
  </div>

  <!-- Emirates Enterprise Deployment & Q1 Pilot Plan -->
  <div class="section-title">
    <span>7. Enterprise Deployment &amp; Emirates Q1 Pilot Plan</span>
    <span style="font-size: 7.2pt; font-weight: normal; color: #6B7280;">Immediate Feasibility</span>
  </div>
  <div class="pilot-timeline">
    <div class="pilot-step">
      <h5>Weeks 1–2: Connect &amp; Tune</h5>
      <p>Deploy offline Docker container inside Emirates private cloud; mount read-only replicas of Core HR, Payroll &amp; AD; tune mappings.</p>
    </div>
    <div class="pilot-step">
      <h5>Weeks 3–4: Critical Triage</h5>
      <p>5 Data Stewards triage top critical queue (ghost payroll &amp; zombie logins). Weekly cryptographic audit review by Internal Audit.</p>
    </div>
    <div class="pilot-step">
      <h5>Weeks 5–6: Expand &amp; Score</h5>
      <p>Onboard Learning LMS and 2 extra systems; publish live Trust Index for WPS &amp; GCAA reports; agree production rollout criteria.</p>
    </div>
  </div>

  <div style="background: #FDF8F6; border: 1px solid #F3D9D2; border-radius: 5px; padding: 5px 8px; margin-top: 6px; font-size: 7.2pt;">
    <b>Team &amp; Pilot Readiness:</b> VeritasHR is built with zero data-science maintenance overhead. The pilot is led by a single Technical Lead (the author) working alongside existing Emirates HR data stewards (no new hiring required). Modular connectors allow any of Emirates' remaining 46+ systems to onboard in minutes.
  </div>

  <div class="footer-note">
    <span>VeritasHR: Solution Note | Page 2 of 2</span>
    <span>Emirates Group HR Data Quality Challenge (Ignyte)</span>
    <span>Confidential - For Competition Evaluation Only</span>
  </div>
</div>

</body>
</html>
"""

def generate_pdf():
    tmp_html = os.path.join(BASE, "docs", "_visual_note.html")
    with open(tmp_html, "w", encoding="utf-8") as f:
        f.write(HTML_CONTENT)

    with sync_playwright() as p:
        b = p.chromium.launch(channel="msedge")
        page = b.new_page()
        page.goto("file:///" + tmp_html.replace(os.sep, "/"))
        page.pdf(path=OUT, format="A4", print_background=True, prefer_css_page_size=True)
        b.close()

    if os.path.exists(tmp_html):
        os.remove(tmp_html)

    doc = fitz.open(OUT)
    print(f"Generated visual PDF: {OUT}")
    print(f"Total Page Count: {len(doc)}")
    for i, page in enumerate(doc):
        links = page.get_links()
        print(f"Page {i+1} has {len(links)} links")
    doc.close()

if __name__ == "__main__":
    generate_pdf()
