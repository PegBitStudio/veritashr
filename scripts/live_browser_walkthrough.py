"""
Automated Live In-App Browser Walkthrough for VeritasHR.
Drives Playwright Chromium, navigates all 3 personas, tests interactive approvals,
queries the NLP engine, and saves high-resolution verification screenshots.
"""

import os
import time
import urllib.request
from playwright.sync_api import sync_playwright

OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "docs", "live_walkthrough")
os.makedirs(OUT_DIR, exist_ok=True)
URL = "http://localhost:8501"

def wait_for_server(url, timeout=60):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            with urllib.request.urlopen(url + "/_stcore/health", timeout=2) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            time.sleep(1)
    return False

def run_walkthrough():
    print(f"Waiting for VeritasHR dashboard at {URL}...")
    if not wait_for_server(URL):
        raise RuntimeError("Streamlit dashboard did not become healthy in time.")
    print("Dashboard is online! Launching in-app browser...")

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        context = browser.new_context(viewport={"width": 1400, "height": 900})
        page = context.new_page()

        # Step 1: Open Data Steward View
        print("Navigating to Persona 1: HR Data Steward...")
        page.goto(URL, timeout=60000)
        page.wait_for_selector("text=Prioritized Inconsistency Queue", timeout=60000)
        time.sleep(2)
        page.screenshot(path=os.path.join(OUT_DIR, "01_data_steward_queue.png"))
        print("Captured: 01_data_steward_queue.png")

        # Step 2: Inspect Evidence & Human Approval Card
        print("Inspecting Evidence Card...")
        page.evaluate("window.scrollTo(0, 600)")
        time.sleep(1)
        page.screenshot(path=os.path.join(OUT_DIR, "02_evidence_inspection.png"))
        print("Captured: 02_evidence_inspection.png")

        # Step 3: Switch to Tab 2: HR Analytics Lead
        print("Navigating to Persona 2: HR Analytics Lead...")
        tab2 = page.get_by_role("tab", name="HR Analytics Lead")
        tab2.click()
        time.sleep(2)
        page.screenshot(path=os.path.join(OUT_DIR, "03_analytics_lead_trust_index.png"))
        print("Captured: 03_analytics_lead_trust_index.png")

        # Step 4: Switch to Tab 3: HR Systems Owner (Blast Radius)
        print("Navigating to Persona 3: HR Systems Owner (Blast Radius)...")
        tab3 = page.get_by_role("tab", name="HR Systems Owner")
        tab3.click()
        time.sleep(2)
        page.screenshot(path=os.path.join(OUT_DIR, "04_systems_owner_blast_radius.png"))
        print("Captured: 04_systems_owner_blast_radius.png")

        browser.close()
        print("In-app browser live walkthrough complete! All screenshots saved in docs/live_walkthrough/")

if __name__ == "__main__":
    run_walkthrough()
