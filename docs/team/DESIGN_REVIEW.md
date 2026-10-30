# DESIGN_REVIEW: vaccine-assay-pipeline site

Seat: Design Lead. Date: 2026-10-30. Scope: the Quarto site in `site/` (6 pages), rendered to `site/_site`.
Theme: pharma, calm and clinical (light default, selected dark mode). All data SYNTHETIC.

## What was built

| Page | Takeaway title | Creative interaction | Table twin |
|---|---|---|---|
| `index.qmd` Overview | "A made-up vaccine trial, checked end to end: 13 of 13 planted problems caught" | 5 KPI tiles (3-layer drill: tile, chart, table plus method); "1 dot = 1 volunteer" unit chart with guess-then-reveal; visit/arm cross-filter drives unit chart, GMT chart, both tables and the "what this means" box | yes (2) |
| `tube.qmd` Follow one tube | "Follow one tube: its digital seal breaks exactly where we tampered" | Play/pause/back/next stepper over 5 custody steps with stored vs recomputed SHA-256 seal; tamper switch for INJ-7 (real stored row vs a replay of the original row, rebuilt and proven by reproducing the stored seal) and INJ-11 (live record vs audit row); real `audit.chain_verify` and `audit.record_reconciliation` output | yes |
| `qc.qmd` Lab QC | "11 of 13 plates passed, and the 2 rejects are the 2 we broke on purpose" | Plate wall (13 buttons, accept/reject); rule slicer dims plates and highlights wells; 96-well map; 4PL curve with shaded LLOQ–ULOQ band and plain-words box | yes (2) |
| `scorecard.qmd` Did we catch it? | "Yes: all 13 planted problems, each by the check meant to catch it" | Category filter; 13 one-sentence stories; false-alarm counts; ends on the strongest true result (peak-end) | yes |
| `glossary.qmd` | 33 terms, search box, source tag per term | Every acronym on every page auto-links here with a hover **and focus** tooltip (Esc dismisses) | n/a |
| `about.qmd` | "One command, eight steps, every number traceable" | 8-step pipeline diagram (HTML, reflows to 1 column); method; honesty notes | n/a |

Every page carries the SYNTHETIC banner and a status badge (SYNTHETIC, last pipeline run UTC, pytest 245/245,
dbt 145/145, seed, rule version, git SHA), read from `site/data/meta.json`.

## Data path and honesty

- `site/build_data.py` reads `docs/results.json`, `data/marts/*.csv` and the read-only DuckDB file and writes 7 small
  JSON files (335 KB total) to `site/data/`. No DuckDB-WASM, no server.
- It uses the pipeline's own `is_seroresponder()` and `compute_row_hash()`. It asserts that per-volunteer
  seroresponse counts equal `mart_immunogenicity` for every group and visit, and that the rebuilt pre-tamper INJ-7
  row reproduces the stored hash. Both asserts passed.
- Headline numbers are truncated, never rounded up (96.5%, 19.7x, likely range 88.0–99.5%). Ratio KPI shows both
  absolute GMTs (4,332 vs 219 AU/mL).
- `site/data/glossary.json` is hand-written: each term is tagged checked / reference / project / unverified.

## Chartability-style fast pass (2026-10-30)

| Check | Result | Evidence |
|---|---|---|
| Text contrast ≥ 4.5:1 | PASS | Token pairs computed with the WCAG formula: lowest light 4.56 (`#6b7785` marks on white; text uses `--muted #56657a` 5.94), status text on tinted bg 5.41–5.75 (green fixed from 4.48 to `#166b2c`); dark 6.38–13.8 |
| Graphics contrast ≥ 3:1 | PASS | Vaccine `#2a78d6` 4.42, placebo `#eb6834` 3.20 (light); `#3987e5` 4.48, `#d95926` 4.20 (dark) |
| Colourblind-safe palette | PASS (2 series) | dataviz `validate_palette.js`: blue/orange pass lightness, chroma, CVD and normal-vision checks in both modes. A grey third slot failed the chroma floor, so grey is used only as a neutral, never as a series |
| Colour never alone | PASS | ✓/✗ icons + words; filled vs hollow vs dashed dots; circle vs square for arms; S/H/L/B letters and "!" on wells; × for failed standards, △ for out-of-range samples |
| Table fallback | PASS | Every chart has a "View as table" `<details>` |
| Bars from zero | n/a | No bar charts. The GMT chart is a dot-and-whisker on a **log** scale, called out in the subtitle |
| n shown | PASS | n on tiles, unit chart panel labels, tooltips and tables |
| Uncertainty in words | PASS | "Likely range" sentences for seroresponse and GMT |
| Motion | PASS | Only motion: 0.5 s reveal fade, disabled under `prefers-reduced-motion`. The tube player advances only after Play and has Pause; slower under reduced motion |
| Keyboard | PASS (by construction) | All controls are native inputs or `<button>`s with visible 3px focus rings; tooltips open on focus. Not tested with a real screen reader |
| Scroll-jacking | PASS | None |
| Mobile 375 px | PASS | Measured in headless Chrome: `scrollWidth` = 375 on all 6 pages after fixes; wide tables scroll inside their own box; one column under 768 px |
| Touch targets ≥ 44 px | PASS | Buttons, radios, selects, summaries set to 44 px min height |
| Dark mode | PASS | Selected tokens (not inverted), screenshot checked on Lab QC |
| Font size | PASS | 18 px base desktop, 17 px phone; chart text 13 px |

## Known gaps (honest)

- Page titles are static text. They match `docs/results.json` at build time, but a re-run with a different seed
  would need the titles edited (the tiles and charts update by themselves).
- Plot tooltips on single dots/wells are mouse-only; keyboard users get the same data from the table twins.
- Observable Plot loads from the jsDelivr CDN at view time (Quarto's OJS runtime), so the site needs internet.
- The 375 px screenshots use an iframe harness inside headless Chrome (headless has a minimum window width), so
  they are a true 375 px layout, not a real phone.
- No real screen-reader test (NVDA/VoiceOver) yet.

## Screenshots

`docs/img/site/{overview,results,tube,qc,scorecard,glossary,about}-{1440,375}.png` (refreshed in the rebuild below), taken with the installed Chrome
headless. The overview uses `?reveal=1` and the tube page `?tamper=1&step=4`; these URL options only pre-set the
controls for screenshots and shareable links.

## Rebuild

```
.venv\Scripts\python -m pipeline.run          # ~40 s, only if data/ is missing
.venv\Scripts\python site\build_data.py       # writes site/data/*.json
"C:\Program Files\Quarto\bin\quarto.exe" render site   # writes site/_site
```
Publishing later: `quarto publish gh-pages site` (Michael's call; nothing was pushed).

---

# Rebuild, 2026-10-30 (evening): the overview as a "production story"

Inputs: `docs/team/USER_TESTING.md` (8 personas, 19 fixes), `dev-team/research/vaccine-rnd-assay-workflow-2026-10-30.md`
(section 6 exec pattern, Prevnar 20 dates), `dev-team/research/audience-data-2026-10-30.md` (VP median age about 52,
directors about 64: restrained theme, purposeful motion, no neon/3D/parallax, at most about 3 sourced numbers per
screen, every headline number within 2 clicks of its source), and Michael's direction relayed by the EM: clean and
calm with bold moments, cinematic but never blocking, guess game removed, "rule of cool" (product launch / lab
instrument feel) as long as it stays readable for a VP.

**Three-line context.** Who: a pharma VP or a 64-year-old board member with 30 seconds to 3 minutes. Must know: is
it on track, and can the numbers be trusted. Should do: approve the Day 29 report once 2 open items are closed.

## Page structure (index.qmd)

| # | Block | Headed by its answer | Key number (counts up once) | Interaction |
|---|---|---|---|---|
| 0 | Verdict (above the fold at 1280x720; static text, no JS needed) | "On track", 2 items need a decision | 56 of 58 vs 0 of 60 · 13 of 13 caught, 0 plates rejected without cause · Tamper detected ✓ at row 2,130 of 6,500 | Each number has a "Source:" link to its deep page (1 click); "Skip the story" link |
| 1 | Where this sits | Lab testing is the ruler for the trial's main result | About 8 years (Prevnar 20, first FDA meeting to approval) | Stage strip with "this demo" marked; Prevnar 20 timeline whose events pop in along the year axis; labelled PUBLIC REFERENCE DATA, FDA memo cited |
| 2 | The vaccine worked | 56 of 58 vs 0 of 60 by Day 29 | 56 | **Rising antibodies** (pinned chart, 5 text steps) |
| 3 | Lab checks | 11 of 13 plates accepted, both rejects were test problems | 11 | **Inside the plate reader** (play/pause) + 13-plate wall |
| 4 | Problems caught | 13 of 13, each by the check meant to catch it | 13 | Three columns of ticks that land one by one |
| 5 | Tampering | Detected at the exact row edited, row 2,130 of 6,500 | 2,130 | **Chain of padlocks** (run the check again) |
| 6 | Decision | Approve the Day 29 report after 2 open items are closed | none | Status (GREEN/AMBER/no target) per milestone with confidence, the decision being asked, honest caveat |
| — | All results on one table (target of "Skip the story") | | | Static table; each row links to its deep page |

Chapter rail: a fixed list on the right at 1400 px and wider; a wrapped row of chapter links under the verdict on
smaller screens. It marks the current chapter (`aria-current`) and holds the global **Pause motion** button. The
guess game is removed (Michael). The visit/group explorer moved to a new deep page, `results.qmd`.

Numbers above the fold are written into the HTML at render time from `site/_variables.yml`, which
`site/build_data.py` writes from `docs/results.json` and the marts. The script stops the build if the "On track"
verdict is no longer supported (not all problems caught, a false plate rejection, no tamper detected, or the vaccine
and placebo response intervals overlap). The results and scorecard page titles also use these values.

## Animation choreography (for Michael to react to)

Rules for every item: it plays once; it is triggered by normal scrolling or a button (no scroll-jacking, no
parallax, no loops); each transition is 750 ms or less (count-ups 700 ms); the final value is always in the HTML
first; **Pause motion** stops all of it and shows the end state; `prefers-reduced-motion: reduce` gives the same
story with no movement.

| Moment | What moves | Timing | Pause / static equivalent |
|---|---|---|---|
| Chapter entrance | Each chapter's blocks fade up 14 px, staggered 60 ms | 380 ms each; the last starts at 240 ms | Everything visible at once |
| Key number | Counts from 0 to the real value, ease-out, tabular digits so the width never jumps | 700 ms, once, when 60% visible | Screen readers get the final value from a hidden copy; the counting copy is `aria-hidden` |
| Prevnar 20 track | The 8 numbered events pop onto the year axis in time order; the 3-year delay is a dashed amber bar | 300 ms each, spread over 750 ms | Static track plus a numbered list (the list is the content; the track is `aria-hidden`) |
| **Rising antibodies** (wow 1) | 120 dots, one per volunteer, keyed by ID so the same dot persists. Step 1: Day 1 levels (log scale). Step 2: vaccine dots lift to their Day 29 level; placebo dots stay. Step 3: dots that rose at least 4 times fill in. Step 4: the same dots slide into a 10-wide unit grid (56 of 58 vs 0 of 60). Step 5, Day 57: dots that no longer meet the rule empty and move to the end of the row (49 of 60) | 750 ms per step, per-dot stagger up to 260 ms so the cloud lifts off | The chart pins only at 900 px wide and 600 px tall or more, with motion on. Otherwise (phone, 200% zoom, reduced motion, Pause) each step gets its own still chart under its text |
| **Inside the plate reader** (wow 2) | A read head sweeps columns 1 to 12 of PLATE-004; each well lights to the yellow of its real OD (the color of a stopped ELISA reaction), with a soft glow only on the brightest wells; flagged wells show a dashed ring and "!" | 130 ms per column, about 1.6 s in all; starts once when the panel is 40% visible | Play/Pause button; reduced motion or Pause shows the fully lit plate |
| Problems caught | 13 cards slide in 10 px, staggered 70 ms within each column | 300 ms each | All visible at once |
| **Chain of padlocks** (wow 3) | The verify check walks left to right; each closed padlock turns teal; at row 2,130 the shackle springs open and the lock turns vermillion with one soft pulse; rows after it go dashed, "untrusted until investigated" | 130 ms per lock; opens at about 1 s | "Run the check again" button; static shows the final open lock and the real verify output |

Considered and parked ("next"): semantic zoom from trial to well (strong idea, but a large build and hard to keep
readable at 200% zoom); a plan-vs-actual Gantt for our synthetic program (would need invented dates).

## User-testing fixes (all 19)

| # | Fix | Status | Where / evidence |
|---|---|---|---|
| 1 | Controls collapse at 520–767 px | FIXED: Observable Inputs stack (label above, input full width) below 768 px; radios no longer shrink | site.css; at 640 px radios are 21 px wide at x = 37 |
| 2 | One-line verdict above the fold | FIXED: hero verdict; status chips collapsed to one line plus "Run details" | index.qmd, site.js; hero ends at 555 px of 720 |
| 3 | Copy buttons in tab order | FIXED: `code-copy: false` | _quarto.yml; 0 on all 7 pages |
| 4 | Forced colors: selected plate/step invisible | FIXED: Highlight outline; double borders for rejects and misses; GrayText for disabled | site.css `@media (forced-colors: active)`; overview-forced-colors.png |
| 5 | "✗ Broken" reads as failure | FIXED: "Tamper detected ✓" in the ok color | index.qmd hero, chapter 5 |
| 6 | Missing headings | FIXED: QC (Pick a plate, Inside the plate, Reference curve, Flags); Scorecard (The 13 problems); Tube (Play the tube's journey, What the real check said); Results (3 H2s) | headings audit |
| 7 | Groups and slider unnamed | FIXED: radio/checkbox forms get `role=radiogroup/group` + `aria-labelledby`; ranges get an `aria-label` | site.js `enhance()`; audit: every input named |
| 8 | No skip link | FIXED: "Skip to main content", visible on focus | _banner.html; 7 of 7 pages |
| 9 | Game spoils itself | REMOVED with the guess game (Michael's call) | — |
| 10 | Science wording | FIXED on site text: "higher dilution (for example 1 in 1,000)"; INJ-6 now quotes the real duplicate CV from the QC flag (50.5%, 51.2%, 51.8%) against the 20% limit. Noted for analytics-engineer in HANDOFF | qc.qmd, scorecard.qmd |
| 11 | Chart text 10–13 px | FIXED: `--chart-font: .85rem` (15.3 px desktop, 14.5 px phone; grows with text zoom); well letters use it too | audit: 0 visible SVG text under 14 px |
| 12 | Idioms | FIXED: removed "by a wide margin", "behind the system's back", "drag it up", "made-up", "re-credited", "flip", "Did we catch it?", "hand-checked", "planted" (now "added on purpose" / "test problem"); "fingerprint" replaced by "seal" | all .qmd |
| 13 | Density; glossary links | FIXED: hero shows 3 numbers; each glossary term is linked once per page (later uses become plain text) | site.js `dedupe()` |
| 14 | Deuteranopia ok/bad | FIXED: ok = teal `#006b54` (dark `#4fd1ac`), bad = vermillion `#b03a0a` (dark `#ff9466`), plus a hatch on rejected plates and dashed rings on flagged wells | theme-*.scss; contrast 5.3–9.5:1 on each background used |
| 15 | Status badge `aria-live` | FIXED: removed | _status.qmd |
| 16 | GMR label, "drag it up", "(95% CI)" | FIXED | results.qmd, index.qmd |
| 17 | Table captions/scope; raw-URL links; job-ad source | FIXED: caption + `scope=col` on every table; glossary links show source titles; the LIMS source is now ASTM E1578 (tag "reference") | site.js, glossary.qmd, glossary.json |
| 18 | "QCflags" spacing | FIXED: summaries use `display: list-item` | site.css |
| 19 | colour/color | FIXED: US English | glossary.json, qc.qmd, about.qmd |

## Panel re-run (headless Chrome 156 via CDP)

7 pages x 6 conditions (1440x900, 1280x720, 640x900, 375x800, forced-colors, reduced-motion) = 42 runs, plus
scroll-step runs of the story chapters. Results: OJS errors 0 of 42; page wider than the viewport 0 of 42; copy
buttons 0; skip link 42 of 42; visible SVG text under 14 px 0; unnamed inputs 0 (after a radio flex-shrink fix on the
tube page); tables without a caption 0; `aria-live` status badges 0. At 1280x720 the verdict block (badge, 3
numbers, sources, skip link) ends at 555 px. Screenshots in `docs/img/site/`: overview-1440, overview-375,
overview-forced-colors, story-rise-1440, story-reader-1440, story-chain-1440, results-640, and the 1440/375 pair
for every page.

## Chartability critical tests (story page)

| Test | Result |
|---|---|
| Low contrast | PASS (text 4.5:1 or more; stage panels use light-on-dark tokens, marks 4.2:1 or more) |
| Content only visual | PASS (every step states its numbers in text; the all-results table repeats them all) |
| Small text | PASS (0 SVG text under 14 px) |
| Seizure risk | PASS (no flashing; one 600 ms pulse) |
| Not keyboard accessible | PASS (native buttons; the rail is links) |
| No table fallback | PASS (all-results table; per-chart tables on the deep pages) |
| No explanation of purpose or how to read | PASS (each heading states the answer; step text explains the encoding) |
| Reading level inappropriate | PASS with care (short sentences, idioms removed; not scored with a formula) |
| Motion not controllable | PASS (Pause motion, reduced motion, play/pause and replay buttons) |
| User style change not respected | PASS (forced colors checked; text zoom grows chart text) |
| Color alone | PASS (filled vs hollow, ✓/✗ words, hatch, dashed rings) |
| Uncertainty not shown | PASS (95% confidence interval in step 4, the status table and the summary) |
| Data density too high | PASS (hero: 3 numbers; one idea per chapter) |
| Synthetic vs public labelling | PASS (banner on every page; Prevnar data labelled PUBLIC REFERENCE DATA) |

## Known gaps (honest)

- `quarto render site` cannot delete `site/_site` while the local preview server holds it open on Windows (os error
  32). I rendered with `quarto render site --output-dir _build` (7 of 7 pages, no warnings) and copied the result
  into `site/_site`. A plain `quarto render site` will work once the server is stopped.
- Chrome keeps author colors inside SVG under forced colors, so the dark stage panels keep their own colors there.
  The text around each chart carries the same facts.
- Per-dot tooltips are mouse-only (`<title>`); the deep pages' tables cover keyboard and screen-reader users.
- No real screen-reader (NVDA/VoiceOver) test and no real phone; the 375 px runs are Chrome device emulation.
- The Prevnar 20 dates are as summarized by our research note from the FDA memo; I did not re-open the PDF.
- Takeaway titles were not restated by a separate reader (playbook rule 12): next step for ux-researcher.
