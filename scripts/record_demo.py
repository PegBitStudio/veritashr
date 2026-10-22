"""
Records the VeritasHR demo video automatically.

  1. Generates narration per scene with the offline Windows voice (System.Speech; nothing leaves the machine).
  2. Starts the dashboard on a spare port with a throw-away audit log.
  3. Drives a Chromium browser through the demo with Playwright, showing subtitles, and records it.
  4. Places each narration clip at the moment its scene started and muxes everything to MP4 with ffmpeg.

Usage:  python scripts/record_demo.py [--data data/raw] [--voice "Microsoft Zira Desktop"] [--out docs/demo_video.mp4]
Needs (dev only): pip install playwright && python -m playwright install chromium ; ffmpeg on PATH ; Windows.
"""

import os
import sys
import time
import wave
import shutil
import argparse
import tempfile
import subprocess
import urllib.request

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = 8599
W, H = 1600, 900

SCENES = [
    ("intro",
     "Emirates HR runs more than fifty systems. The same employee lives in many of them, with different I.D.s and formats. "
     "Fixing data in one place can quietly break payroll or security somewhere else, so people are afraid to fix anything. "
     "This is VeritasHR. It finds the problems, explains them, ranks them, and shows what a fix would touch, before anyone approves it.",
     "VeritasHR finds, explains and ranks HR data problems, and shows what each fix touches before anyone approves it."),
    ("mapping",
     "It reads messy data as it is. VeritasHR works out which file is payroll, and which column holds the employee I.D., from the values themselves. "
     "On a scrambled copy of the data, with renamed columns, new date formats and missing I.D.s, it gave the same result.",
     "Files and columns are recognised automatically, and every mapping decision is shown."),
    ("queue",
     "For the data steward, issues are ranked by business impact. Number one: Ayesha Dubois. "
     "Core HR says she left in November twenty sixteen, but payroll still pays her twenty five thousand five hundred dirhams a month.",
     "Ranked by business impact. #1: left in 2016, still paid AED 25,500 a month."),
    ("evidence",
     "Here is the evidence side by side, with Core HR marked as the system of record, and the suggested fix: set pay status to inactive. "
     "Every suggestion shows its source and its reasoning.",
     "Evidence side by side. Core HR is the system of record. Suggested fix: pay status INACTIVE."),
    ("approve",
     "Nothing changes automatically. I approve the fix under my own name. "
     "The decision goes into an audit trail where every entry is chained by hash, so if anyone edits the history, it shows. "
     "System owners download only the approved changes.",
     "A named person approves every fix. Decisions are hash-chained, so tampering is detected."),
    ("impact",
     "The systems owner sees the ripple effect before approving, read straight from the dependency file: "
     "the bank salary feed, the wages protection file, and the headcount dashboard.",
     "Impact before approval: feeds and reports that this change touches, from dependencies.md."),
    ("trust",
     "The analytics lead sees which numbers to trust. Each report's score is the share of records behind it with no open issue. "
     "The headcount and payroll reports are over ninety five percent clean, but flagged not safe to file while critical cases are open.",
     "Trust = share of records with no open issue. Not safe to file while critical issues are open."),
    ("ask",
     "Ask a question in plain language. How many active employees in Dubai? Two thousand, four hundred and eighty nine. "
     "It shows how it read the question, the source it used, and a warning: fifteen more people probably belong here, but their location code is invalid.",
     "Answers show the interpretation, the source, and data-quality caveats."),
    ("refuse",
     "And if it cannot answer, it says so, instead of guessing.",
     "No guessing: unknown questions are declined."),
    ("close",
     "On the sample pack, VeritasHR found all two hundred and fifty five planted errors, and in a blind test it found eighty out of eighty new error types it was never built for. "
     "It runs fully offline in one container, so no data leaves Emirates. A new source is a file drop, not a code change. We are ready for a pilot next quarter.",
     "255/255 planted errors · 80/80 blind new-type errors · offline · pilot-ready."),
]

def tts(text, path, voice):
    ps = (
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        f"$s.SelectVoice('{voice}'); $s.Rate = 0; "
        f"$s.SetOutputToWaveFile('{path}'); "
        f"$s.Speak([Console]::In.ReadToEnd()); $s.Dispose()"
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], input=text, text=True, check=True)
    with wave.open(path) as w:
        return w.getnframes() / w.getframerate()

def audio_seconds(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                         capture_output=True, text=True, check=True).stdout
    return float(out.strip())

def wait_for_server(url, timeout=120):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            urllib.request.urlopen(url + "/_stcore/health", timeout=2)
            return
        except Exception:
            time.sleep(1)
    raise RuntimeError("dashboard did not start")

SUB_JS = """(t) => {
  let el = document.getElementById('veritas-sub');
  if (!el) { el = document.createElement('div'); el.id = 'veritas-sub';
    el.style.cssText = 'position:fixed;left:50%;bottom:28px;transform:translateX(-50%);max-width:80%;z-index:999999;' +
      'background:rgba(20,20,20,.85);color:#fff;font:600 20px/1.35 Helvetica,Arial,sans-serif;padding:12px 22px;border-radius:10px;text-align:center;';
    document.body.appendChild(el); }
  el.textContent = t; el.style.display = t ? 'block' : 'none';
}"""

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=os.path.join(BASE, "data", "raw"))
    ap.add_argument("--voice", default="Microsoft David Desktop")
    ap.add_argument("--out", default=os.path.join(BASE, "docs", "demo_video.mp4"))
    ap.add_argument("--narration-dir", help="Folder with pre-recorded <scene>.mp3/.wav clips (e.g. ElevenLabs or your own voice); "
                                            "falls back to the offline Windows voice for any scene without a clip")
    args = ap.parse_args()
    from playwright.sync_api import sync_playwright

    work = tempfile.mkdtemp(prefix="veritas_demo_")
    print("Narration...")
    clips = {}
    for name, text, _ in SCENES:
        pre = [os.path.join(args.narration_dir, f"{name}{ext}") for ext in (".mp3", ".wav", ".m4a")] if args.narration_dir else []
        pre = next((f for f in pre if os.path.exists(f)), None)
        if pre:
            clips[name] = (pre, audio_seconds(pre))
        else:
            clips[name] = (os.path.join(work, f"{name}.wav"), tts(text, os.path.join(work, f"{name}.wav"), args.voice))
    total = sum(d for _, d in clips.values())
    print(f"  narration {total:.0f}s")

    env = dict(os.environ, VERITAS_DATA_DIR=args.data, VERITAS_AUDIT_LOG=os.path.join(work, "audit.jsonl"))
    server = subprocess.Popen([sys.executable, "-m", "streamlit", "run", os.path.join(BASE, "ui", "app.py"),
                               "--server.headless=true", f"--server.port={PORT}", "--browser.gatherUsageStats=false"],
                              cwd=BASE, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    starts = {}
    try:
        url = f"http://localhost:{PORT}"
        wait_for_server(url)
        with sync_playwright() as p:
            browser = p.chromium.launch()
            # Warm-up visit so the pipeline result is cached before recording starts
            warm = browser.new_page(viewport={"width": W, "height": H})
            warm.goto(url); warm.get_by_text("Prioritized Inconsistency Queue").wait_for(timeout=180000); warm.close()

            ctx = browser.new_context(viewport={"width": W, "height": H}, record_video_dir=work,
                                      record_video_size={"width": W, "height": H})
            page = ctx.new_page()
            t0 = time.monotonic()
            page.goto(url)
            page.get_by_text("Prioritized Inconsistency Queue").wait_for(timeout=120000)
            video_offset = time.monotonic() - t0  # loading time trimmed from the video later

            def scene(name, actions):
                _, text, sub = next(s for s in SCENES if s[0] == name)
                starts[name] = time.monotonic() - t0
                page.evaluate(SUB_JS, sub)
                a0 = time.monotonic()
                actions()
                remaining = clips[name][1] + 0.6 - (time.monotonic() - a0)
                if remaining > 0:
                    page.wait_for_timeout(int(remaining * 1000))

            def smooth(locator):
                locator.first.evaluate("e => e.scrollIntoView({behavior: 'smooth', block: 'center'})")
                page.wait_for_timeout(1200)

            def top():
                page.evaluate("() => document.querySelectorAll('*').forEach(e => { if (e.scrollTop > 0) e.scrollTo({top: 0, behavior: 'smooth'}) })")
                page.wait_for_timeout(1000)

            scene("intro", lambda: page.wait_for_timeout(500))

            def mapping():
                page.get_by_text("Column auto-mapping report").click()
                page.wait_for_timeout(800)
            scene("mapping", mapping)

            def queue():
                page.get_by_text("Column auto-mapping report").click()
                smooth(page.get_by_text("Showing", exact=False))
            scene("queue", queue)

            scene("evidence", lambda: smooth(page.get_by_text("Cross-System Evidence Trail")))

            def approve():
                box = page.get_by_label("Your name / staff ID", exact=False)
                box.click(); box.type("steward.demo", delay=60); box.press("Enter")
                page.wait_for_timeout(1500)
                btn = page.get_by_role("button", name="Approve Fix")
                smooth(btn)
                btn.first.click()
                page.wait_for_timeout(2500)
                smooth(page.get_by_text("Decision Audit Trail"))
            scene("approve", approve)

            def impact():
                top()
                page.get_by_role("tab", name="HR Systems Owner", exact=False).click()
                page.wait_for_timeout(1500)
                smooth(page.get_by_text("Proposed Fix:", exact=False))
            scene("impact", impact)

            def trust():
                top()
                page.get_by_role("tab", name="HR Analytics Lead", exact=False).click()
                page.wait_for_timeout(1500)
                smooth(page.get_by_text("Statutory Reports Trust Index", exact=False))
            scene("trust", trust)

            scene("ask", lambda: smooth(page.get_by_text("Interpreted as:", exact=False)))

            def refuse():
                page.get_by_text("Custom Query...").click()
                page.wait_for_timeout(1200)
                box = page.get_by_label("Enter your HR inquiry:")
                box.fill("What will the weather be tomorrow?"); box.press("Enter")
                answer = page.get_by_text("Sorry, I could not map", exact=False)
                answer.first.wait_for(state="visible", timeout=30000)
                smooth(answer)
            scene("refuse", refuse)

            def close():
                top()
                page.evaluate("""() => { const d = document.createElement('div');
                  d.style.cssText = 'position:fixed;inset:0;z-index:99999;background:linear-gradient(135deg,#1A1A1A,#2D0005 55%,#8A000A);color:#fff;display:flex;flex-direction:column;align-items:center;justify-content:center;font-family:Helvetica,Arial,sans-serif;';
                  d.innerHTML = '<div style="font-size:54px;font-weight:700">VeritasHR</div><div style="font-size:24px;opacity:.85;margin:8px 0 36px">One Employee, One Truth</div>' +
                   '<div style="font-size:26px;line-height:1.9;text-align:left">✔ 255 / 255 planted errors found<br/>✔ 80 / 80 blind new-type errors found<br/>✔ Same result on scrambled files and columns<br/>✔ Human approval + tamper-evident audit trail<br/>✔ Runs fully offline in one container</div>';
                  document.body.appendChild(d); }""")
            scene("close", close)
            page.evaluate(SUB_JS, "")
            page.wait_for_timeout(800)
            ctx.close()
            browser.close()
            raw_video = [f for f in os.listdir(work) if f.endswith(".webm")][0]
    finally:
        server.terminate()

    # Audio track: each clip delayed to its scene start (relative to the trimmed video start)
    print("Mixing...")
    inputs, filters = [], []
    for k, (name, _, _) in enumerate(SCENES):
        inputs += ["-i", clips[name][0]]
        delay = max(0, int((starts[name] - video_offset) * 1000))
        filters.append(f"[{k + 1}:a]adelay={delay}|{delay}[a{k}]")
    mix = "".join(f"[a{k}]" for k in range(len(SCENES))) + f"amix=inputs={len(SCENES)}:normalize=0[aout]"
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{video_offset:.2f}", "-i", os.path.join(work, raw_video)] + inputs + [
        "-filter_complex", ";".join(filters) + ";" + mix, "-map", "0:v", "-map", "[aout]",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
        "-shortest", args.out]
    subprocess.run(cmd, check=True)
    shutil.rmtree(work, ignore_errors=True)
    print(f"Done: {args.out}")

if __name__ == "__main__":
    main()
