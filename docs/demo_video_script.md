# VeritasHR: 3-minute demo script

All numbers below are what the dashboard shows on the sample pack. **Re-check them against the screen if you record on the official test set.**

Before recording: run `streamlit run ui/app.py`, type a reviewer name (e.g. `steward.demo`) in the sidebar, and delete `audit/decisions.jsonl` so the trail starts empty.

---

**[0:00–0:20] Problem**
*Screen: dashboard header and KPI row.*
> "Emirates HR runs more than 50 systems. The same employee lives in many of them, with different IDs and formats. Fixing data in one place can break payroll or security somewhere else, so people are afraid to fix anything. VeritasHR finds the problems, explains them, ranks them, and shows what a fix would touch before anyone approves it."

**[0:20–0:45] It reads messy data as it is**
*Screen: sidebar → "Column auto-mapping report" expander.*
> "We don't need clean inputs. VeritasHR works out which file is payroll and which column is the employee ID from the values themselves. We tested it on a scrambled copy of the data, with renamed columns, new date formats and IDs removed, and it got the same result."

**[0:45–1:30] Data steward: evidence and a human decision**
*Screen: Tab 1. The top issue is ERR-GHOST-EK10562.*
> "The queue is ranked by business impact. Number one: Ayesha Dubois. Core HR says she left in November 2016, but payroll still pays her AED 25,500 a month. Here's the evidence side by side, with Core HR marked as the system of record, and the suggested fix: set pay status to inactive."
*Point at "Approving will affect…", then click **Approve Fix**.*
> "Nothing is changed automatically. I approve it under my name. It goes into an audit trail where every entry is chained by hash." *Scroll to the audit trail, showing 🔒 "chain intact".* "If anyone edits the history, this turns red. The system owner downloads only the approved changes."
*Optional: open an INVALID_CODE issue.* "When a code is wrong, it tells you why it suggests the new one. 'EK-FLT-OPS' is a misspelling of 'EK-FLIGHT-OPS'."

**[1:30–2:00] Systems owner: impact before approval**
*Screen: Tab 3, same issue.*
> "The systems owner sees the ripple effect, read directly from the dependency file: the WPS bank feed, the WPS regulatory file and the headcount dashboard. No surprises after approval."

**[2:00–2:40] Analytics lead: which numbers to trust**
*Screen: Tab 2.*
> "Each report gets a trust score: the share of records behind it with no open issue. The WPS payroll file is 96.8% clean, but it's flagged *not safe to file* while 35 critical cases are open."
*Ask: "How many active employees in Dubai?"*
> "2,489. It shows how it read the question, which source it used, and a warning: 15 more people probably belong here, but their location code is invalid. Ask it something it can't answer, and it says so instead of guessing."

**[2:40–3:00] Close**
*Screen: README or the test-results table.*
> "On the sample pack it found all 255 planted errors, and in a blind test it found 80 out of 80 new error types it was never built for. It runs fully offline in one container, with no data leaving Emirates, and a new source is a file drop, not a code change. We're ready for a pilot next quarter."
