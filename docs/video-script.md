# Demo video script (3 minutes)

Record the screen at 1440×900 on the live demo, with English subtitles.
Voice-over in plain English; the problem first, then the technique.

| Time | Screen | Voice-over |
|---|---|---|
| 0:00–0:20 | Deck slides 1–2 | Before a sponsor works with a trial site, it must check that the investigator is not excluded by the HHS Inspector General or debarred by the FDA. The lists are public, over 80,000 people, but scattered, and checked by hand, name by name. |
| 0:20–0:35 | Deck slide 3 | The hard part is identity. Miss a match and the trial is at risk. Flag a namesake and you wrong an innocent doctor. |
| 0:35–0:55 | App: Screen page, drop the demo CSV, show the 5-row preview, click Run screening | Red Flag Radar takes a list of investigators. Here, 300 synthetic investigators. One click. |
| 0:55–1:15 | Results page: counters, sort by score | In under two seconds, every investigator is sorted: probable match, to review, or cleared. The reviewer starts with what needs attention. |
| 1:15–1:50 | Open a "Probable match": side by side, reasons, source link; type a comment, Confirm | Here the investigator and the OIG record agree on name, city, state, specialty and NPI. The reasons are listed in plain words, with a link to the official record. I confirm, and a comment is required. |
| 1:50–2:15 | Back, open a "To review" homonym (same name, other state/specialty); Dismiss with comment | Here is the case that matters: same name, but a different state and specialty. The tool does not accuse; it asks for a look. I dismiss it, with my reason. |
| 2:15–2:35 | Audit log page | Every decision is logged: who, when, why, and which model and list versions were used. Export to CSV or PDF for an audit. |
| 2:35–2:55 | Evaluation page: tiles and precision-recall chart | We measured it on a labeled test set. Red Flag Radar finds 96.7% of sanctioned people, every probable alert is right, and no namesake is marked probable. An exact-name check finds 23% and accuses 27 namesakes. |
| 2:55–3:00 | Deck last slide | Open source on GitHub, running live. Thank you. |

Before recording: reset the demo data (`docker compose down -v && docker compose up -d`) and set the reviewer name in the header.
