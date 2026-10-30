# User testing: interactive site (8-persona panel)

Date: 2026-10-30. Site: http://127.0.0.1:8600 (Quarto build in `site/_site`). Method: headless Chrome 
(Chrome DevTools Protocol, no installed packages) at 1440x900, 1280x720, 640 px wide (equal to a 1280 px laptop at 200% zoom),
375 px, with `forced-colors: active`, `prefers-reduced-motion: reduce`, and the deuteranopia vision filter. A DOM audit
(headings, landmarks, focus order, ARIA, tables, inputs) ran on every page. Each persona's task was then walked through
against the screenshots, the DOM and the `.qmd` sources. Nothing on the site was edited.

Evidence lives in `docs/team/user-testing-img/` (written `img/` below). The raw DOM audit is `img/dom-audit.json`.

---

## 1. Research summary (public sources)

| # | Rule | What it says | Source |
|---|---|---|---|
| R1 | Older adults are slower and less successful | In NN/g tests, users over 65 had a 55% task success rate against 75% for users aged 21-55, and were about 43% slower. Text size and plain navigation matter most. | https://www.nngroup.com/articles/usability-for-senior-citizens/ |
| R2 | NIA/NLM senior-friendly checklist | Readable text (sans-serif, large, high contrast). Avoid auto-moving text. Keep navigation simple and consistent. Reduce memory load. | NIA/NLM "Making Your Web Site Senior Friendly" (archived copy: https://corpora.tika.apache.org/base/docs/govdocs1/460/460056.pdf) |
| R3 | AARP audience heuristics | Chisnell and Redish's heuristics for AARP cover age, ability, aptitude and attitude. Older users are not "unable", but they punish ambiguity and hidden controls. | https://danachisnell.com/older-people-cant-use-technology-refuting-assumptions-through-research/ |
| R4 | Lower-literacy readers read word by word | They do not scan. They "satisfice" on the first plausible item. Plain language helps every reader, experts included. | https://www.nngroup.com/articles/writing-for-lower-literacy-users/ |
| R5 | Jargon | Lead with plain words and put the jargon in parentheses. Repeat the plain version, because readers do not read top to bottom. | https://www.nngroup.com/articles/ux-writing-faqs/ |
| R6 | Plain language standard | GOV.UK writes for a reading age of 9 because it helps experts too. digital.gov/plainlanguage.gov: short sentences, common words, no idioms. | https://www.gov.uk/guidance/content-design/writing-for-gov-uk ; https://digital.gov/topics/plain-language/ |
| R7 | WCAG 2.2 | 1.4.1 Use of Color; 1.4.4 Resize Text and 1.4.10 Reflow (usable at 400% / 320 px); 1.4.11 Non-text Contrast; 1.3.1 Info and Relationships; 2.4.1 Bypass Blocks; 2.4.3 Focus Order; 2.4.6 Headings; 2.4.11 Focus Not Obscured; 2.5.8 Target Size; 3.1.5 Reading Level (AAA); 4.1.2 Name, Role, Value | https://www.w3.org/TR/WCAG22/ |
| R8 | COGA (cognitive and learning disabilities) | Clear purpose up front. Help users find the most important things. Use clear words. Avoid memory tasks. Limit distractions. Give one main idea per chunk. | https://www.w3.org/TR/coga-usable/ |
| R9 | Chartability | 50 heuristics (14 critical) under POUR plus Compromising, Assistive, Flexible. Charts need a text summary, a table alternative, no hover-only data, user control of motion, and should work in high contrast. | https://diglib.eg.org/handle/10.1111/cgf14522 ; https://data.europa.eu/apps/data-visualisation-guide/intro-to-chartability |
| R10 | Screen-reader charts (Highcharts accessibility docs) | Give a visually hidden description, a data-table view, and keyboard navigation through points. Very large point sets should be summarized, not read point by point. | https://highcharts.com/docs/accessibility/accessibility-module |
| R11 | Colorblind-safe palettes | Okabe-Ito (blue #0072B2 / orange #E69F00 / vermillion #D55E00) is safe for deuteranopia. Blue/orange is the most reliable pair. Red/green never works alone, so pair color with shape and text. | https://jianhong.r-universe.dev/colorBlindness/doc/manual.html ; https://siegal.bio.nyu.edu/color-palette/ |
| R12 | Forced colors / Windows High Contrast | The browser replaces author colors with system colors and removes `box-shadow` and background images. Chrome leaves SVG author colors alone. Use `@media (forced-colors: active)` with system keywords (CanvasText, Highlight) for state that is shown only by color or shadow. | https://developer.mozilla.org/en-US/docs/Web/CSS/@media/forced-colors |
| R13 | Executive dashboards, "5-second test" | The main message should land in about 5 seconds. Put 3-5 KPIs at the top left, show status (on track or not) and exceptions, and use one verdict, not a wall of numbers. This is practitioner consensus (eye-tracking F-pattern), not lab law. | https://www.aufaitux.com/blog/good-dashboard-design/ ; https://datavis.readthedocs.io/en/latest/dashboard.html |
| R14 | Scrolljacking hurts | NN/g found that overriding scroll speed or direction harms control, discoverability, efficiency and task success. It is worst when users must read text while it moves. | https://www.nngroup.com/articles/scrolljacking-101/ |
| R15 | Scroll-triggered fades | Keep fade-ins under about 500 ms. Users scroll past content that is still animating and think it is empty. | https://www.nngroup.com/articles/scroll-fading-101/ |
| R16 | Scrollytelling can help comprehension | A 2025 pilot on HPV-vaccination data found a scrollytelling version clearer and easier to follow than a static one, with minor navigation issues. The sample was small. | (pilot reported in search results; treat as weak evidence) |

Takeaway: build for the reader with the least time or ability (the VP, the 68-year-old, the screen-reader user). Everyone else gains from it (R4, R6).

---

## 2. Per-persona findings

Severity key: **B** = blocker, **M** = major, **m** = minor.

### P1. VP of Vaccine R&D, 30 seconds: "are we on track?"
Worked
- The H1 states a result, and the KPI tiles each start with a one-line verdict ("Every planted problem was caught").
- Numbers come with their denominators ("56 of 58"). Honest truncation.

Problems
- **M**: There is no single verdict on the question this reader asks. The H1 answers "did the pipeline catch planted problems". "Did the vaccine work" sits lower, in the H2. Nothing says "On track / Not on track". *img/exec-fold-1280x720.png*. Breaks R13, R8 (purpose up front).
- **M**: On a 1280x720 laptop the fold is taken by the SYNTHETIC banner, a two-line H1, a subtitle, five status chips (`pytest 245 of 245`, `dbt 145 of 145`, `seed 42 · rules QC-RULES-1.0 · build 6b718e9`) and a four-line lede. Only one KPI value ("13") is fully visible. *img/exec-fold-1280x720.png*. Breaks R13.
- **M**: Tile 5 shows a large red "✗ Broken". At a glance it reads as a failure, but it is the good outcome; you have to open "Is 'broken' bad news?" to learn that. *img/exec-fold-1440.png*. Breaks R13 (status must read correctly in 5 s) and R8.
- **m**: Two "times" figures sit close together: "about 19.7 times placebo" (vaccine vs placebo GMT ratio) in the tile, and "rose about 16.6-fold" (GMFR, within the vaccine group) in the H3. A skimmer will conflate them. Breaks R5.
- **m**: Tile notes are in tooling language: "n = 58", "unexplained flag", "EVT-000924", "row 2,130 of 6,500".

### P2. 68-year-old board member and investor, reading glasses, 200% zoom
Worked
- The 18 px root font, 44 px targets, and plain headings phrased as questions ("Did the vaccine work?") are good for R1 and R2.
- At 375 px (phone) everything stacks correctly.

Problems
- **B**: At 640 CSS px (a 1280 px laptop at 200% zoom, or a tablet in portrait) the overview controls vanish. The Visit radios and Groups checkboxes are pushed to x = 616 px (off the right edge), the guess number box is 8 px wide, and the range slider is 0 px wide. The page shows the labels "Visit", "Groups" and "Your guess (%)" above empty space, so this reader cannot pick a visit or make a guess. *img/crop-zoom-controls2.png*; probe output: `radio 616,2044 13x21`, `number 8x29`, `range 0x44`. Cause: in `assets/site.css`, `form[class*="oi-"] { --label-width:100% }` inside the `max-width:767.98px` query wraps label and input, but between roughly 520 and 767 px the Observable Inputs grid keeps the label column at 100% and the input column collapses. Breaks WCAG 1.4.4 and 1.4.10 (R7) and R1.
- **M**: At 200% zoom the first screen shows only the banner, title and chips, with no result. *img/zoom200-fold.png*. Breaks R13 and R2.
- **M**: Chart text is small. Observable Plot is set to 13 px; tick labels, facet labels ("Vaccine (60 volunteers)") and the "valid range (LLOQ to ULOQ)" label render at about 10-12 px, and SVG text does not grow with browser text-only zoom. 264 text elements on the overview are under 14 px. *img/dom-audit.json* (`smallText`). Breaks R2 and R1.
- **m**: In the unit chart at narrow widths the facet labels are cut to "ne" / "bo". *img/crop-zoom-controls2.png*.
- **m**: The page has 29 dotted-underline glossary links, and each opens a hover or focus tooltip. That is a lot of moving targets for unsteady hands. Breaks R2 (simple navigation).

### P3. Low-vision user with Windows High Contrast (forced colors)
Worked
- Text, borders, buttons and links map well to system colors. ✓/✗ glyphs and "Accepted/Rejected" words carry status, so plate and scorecard state survives. *img/fc-qc.png*, *img/fc-scorecard.png*.
- The unit-chart dots keep their filled vs hollow shapes. *img/fc-index-revealed.png*.

Problems
- **M**: The selected plate is invisible. `.plate-wall button[aria-pressed="true"]` uses only `box-shadow`, which forced colors removes. In *img/fc-qc.png*, PLATE-004 is selected but looks exactly like the other 12 plates. The current step in the tube stepper (`.stepper button.current { box-shadow }`) has the same problem. Breaks R12 and WCAG 1.4.11 / 1.3.1.
- **M**: Rejected plates lose their red fill, and caught/missed scorecard cards lose their colored left border. Text still carries the state, but scanning 13 plates for the two rejects becomes a reading task. Breaks R12 (scanning aid lost).
- **m**: Chart SVGs keep author colors on a black system background (Chrome behavior, R12). The mid-blue vaccine dots and the grey `--neutral-mark` hollow rings drop toward 3:1 against black, and the GMT whiskers are thin (2 px). There is no `@media (forced-colors: active)` block anywhere in `site.css`.
- **m**: The "Back" button disabled state renders in an odd green (GrayText mapping) in *img/fc-tube.png*.

### P4. Blind screen-reader user (judged from the DOM)
Worked
- `lang="en"`, landmarks (header/nav/main/footer), meaningful page titles.
- Every chart is `role="img"` with a data-bearing `aria-label`, for example "Typical antibody level by visit, log scale. Placebo D1: 225 AU/mL; … Vaccine D29: 4,332 AU/mL…". Every chart also has a "View as table" twin (R9, R10).
- The tube player has `aria-live="polite"`, `aria-current="step"`, labeled step buttons and Pause. The glossary tooltip opens on focus and closes with Esc (WCAG 1.4.13).

Problems
- **M**: 11 invisible "Copy to Clipboard" buttons (Quarto code-copy buttons left over from hidden OJS cells, 12x2 px) are in the tab order on every page. The screen reader announces "Copy to Clipboard, button" between the lede and the KPIs and again before the controls. *dom-audit.json* focusOrder; probe `copybtns 12x2`. Breaks WCAG 2.4.3 and 4.1.2 (R7).
- **M**: There is no skip link (`skip:false` on all six pages), so each page starts with about 10 nav stops. Breaks WCAG 2.4.1.
- **M**: The radio and checkbox groups ("Visit", "Groups", scorecard "Show", tube "Pick a tube") have no `fieldset`/`legend` or `role=radiogroup` with a name (`fieldsets: 0`). The range slider has no accessible name (`unlabeledInputs: ["range"]`). Breaks WCAG 1.3.1 and 4.1.2.
- **M**: Heading structure. On scorecard.html the H1 is followed directly by thirteen H3s ("✓ Caught · P-001"…) with no H2. qc.html has an H1 and nothing else, so the plate wall, well map, curve and flags table have no headings. tube.html has an H1 and one H3. Navigating by headings fails on the deepest pages. Breaks WCAG 1.3.1 and 2.4.6.
- **m**: The status badge is `aria-live="polite"`, so on every page load the reader announces "SYNTHETIC, Last pipeline run 2026-10-30 05:19:55 UTC, pytest 245 of 245 passed…". That is noise. Breaks R8 (limit distractions).
- **m**: Data tables have no `<caption>` and no `scope`. Per-dot data in the unit chart, well map and curve is in hover-only SVG `<title>`s (the table twins cover it, so this is minor). Breaks R9 (no hover-only data).
- **m**: The glossary "source" links use raw URLs as link text ("www.fda.gov/regulatory-information/search-fda-guidance-documents/data-…"), and those get read out character by character.

### P5. Colorblind user (deuteranopia)
Worked
- Vaccine and placebo use blue #2a78d6 and orange #eb6834, a deuteranopia-safe pair (R11). The GMT chart adds circle vs square shapes, and the unit chart adds filled vs hollow plus facet labels. *img/deut-index-revealed.png*.
- Every status has a ✓/✗ glyph and a word, so color is never the only signal (WCAG 1.4.1 met).

Problems
- **m**: Under deuteranopia, the green `--ok` and red `--bad` both become olive/mustard. "✓ Accepted" and "✗ Rejected" plates, the green pytest chip and the yellow SYNTHETIC chip all look the same hue. *img/deut-qc.png*. Text saves it, but the pre-attentive "find the red one" cue is gone. Use a blue/orange (Okabe-Ito) ok/bad pair or add a pattern (R11).
- **m**: Flagged wells are a red ring plus "!". Under deuteranopia the ring reads close to the grey blank wells, so only the "!" (10-12 px) carries the signal. *img/deut-qc.png*.

### P6. Person with ADHD or a cognitive disability
Worked
- Headings ask and answer a question. "What this means" boxes. The guess-then-reveal step is good active engagement (R8 "help users focus"). Motion is user-started, has Pause, and the CSS honors reduced motion.

Problems
- **M**: Information density at the top. The reader meets a banner, 5 chips, a lede with 4 jargon links, then 5 tiles with title, value, note and "details" each, about 20 text blocks before the first chart. *img/exec-fold-1440.png*. Breaks R8 (one idea per chunk; most important first) and R13.
- **M**: The game gives the answer away before the guess. The "What this means" box under the hidden chart already says "56 of 58 vaccinated volunteers responded", and KPI tile 2 shows it too. *img/crop-zoom-controls2.png* vs the overview source (`meaningBox` does not check `revealed`). The task contradicts itself, which confuses. Breaks R8 (clear, consistent tasks).
- **m**: 29 dotted links per page, plus tooltips that pop up on hover, pull the eye around. Link only the first occurrence of each term per page (R5 says repeat the plain word, not the link).
- **m**: The honesty notes are long single paragraphs (tube.html's is about 100 words in one block). Use bullets, as about.html already does.

### P7. Non-native English speaker
Worked
- Mostly short sentences. Numbers are written as numerals. The glossary is in plain English.

Problems
- **M**: Idioms and phrasal verbs: "by a wide margin", "behind the system's back", "drag it up", "re-credited", "made-up", "planted", "flip the tamper switch", "Is 'broken' bad news?", "Did we catch it?", "hand-checked". These break literal translation and browser translate. Breaks R6 (no idioms) and R4.
- **m**: Mixed spelling ("colour" in the glossary and curve axis, "color" elsewhere; "millilitre"). Pick one.
- **m**: Metaphors stacked on jargon: "ruler wells", "seal", "fingerprint", "hash chain". Each metaphor is fine alone, but four for one concept (integrity) is a lot. Keep "seal" only and define it once.

### P8. Lab scientist / assay developer
Worked
- 4PL, LLOQ/ULOQ working range, standard recovery 80-120%, control ±20%, duplicate CV 20%, seroresponse as at least a 4-fold rise (or at least 4x LLOQ if baseline below LLOQ), Clopper-Pearson, t-based CI on log10 GMT, half-LLOQ imputation: all correct and honestly labeled "demo default", with the ICH M10 disclaimer.
- The GMT chart is on a log scale, with an explanation.

Problems (terminology a scientist would flag)
- **M**: "stronger dilution" (qc.html "valid range" box; scorecard INJ-8). Scientists say a **higher (greater) dilution**, such as 1:1,000. "Stronger" is ambiguous because it can mean more concentrated.
- **M**: INJ-6 card: "One duplicate read at 45% of the other… The duplicate check (more than 20% disagreement)". The rule is **%CV > 20%**, and a 45% ratio is about 53% CV (the QC table shows "duplicate OD CV 50.5% > 20.0%"). Saying "disagreement" mixes ratio and CV. Write "the two duplicate wells had a CV of 5x%, above the 20% limit".
- **m**: "about 19.7 times placebo" should be labeled **GMR (geometric mean ratio)** for this audience, and kept clearly separate from GMFR.
- **m**: "GMT is a geometric mean, so one very high volunteer cannot drag it up." It is *less sensitive* to one high value, not immune. Overstated.
- **m**: "the true vaccine response rate is likely between 88.0% and 99.5%." This is the common Bayesian reading of a frequentist CI. Acceptable for lay readers, but add "(95% confidence interval)" next to it for scientists, as the tile details already do.
- **m**: "Curve fit well (R² 0.9997)". Note that R² is a weak acceptance criterion for 4PL; the demo-default note covers it.
- **m**: The glossary cites a BioSpace job posting as a source for the LIMS definition. That hurts credibility with this reader.

---

## 3. Prioritized fix list

Seats: design-lead (DL), analytics-engineer (AE, owns `build_data.py`/content numbers), qa-engineer (QA), product-owner (PO).

| # | Sev | Issue | Fix | Owner | Evidence | Rule |
|---|---|---|---|---|---|---|
| 1 | B | Overview controls collapse to 0-8 px between about 520 and 767 px (200% zoom, tablets) | In `site.css`, apply the stacked layout (`form[class*="oi-"]{display:block}` with the label above the input, input `width:100%`) at `max-width:767.98px` for real. Add a QA check at 640 px and 768 px. | DL (+QA) | img/crop-zoom-controls2.png | WCAG 1.4.4, 1.4.10; R1 |
| 2 | M | No one-line "are we on track" verdict above the fold | Add a verdict strip as the first element after the H1: "On track: vaccine response 96% vs 0% placebo · pipeline caught 13/13 planted problems · 0 false plate rejections". Move the status chips below the KPIs or collapse them into one "Run details" chip. | PO + DL | img/exec-fold-1280x720.png | R13, R8 |
| 3 | M | Invisible "Copy to Clipboard" buttons in the tab order (11 per page) | Set `code-copy: false` in `_quarto.yml` (format html), or `echo: false` with no code-copy. | DL | dom-audit.json focusOrder | WCAG 2.4.3, 4.1.2 |
| 4 | M | Selected plate and current tube step invisible in forced colors | Add `@media (forced-colors: active){ .plate-wall button[aria-pressed=true], .stepper button.current { outline:3px solid Highlight; outline-offset:2px } .plate-wall button.rej, .score-card.miss { border-style:double; border-width:4px } }`. | DL | img/fc-qc.png, img/fc-tube.png | R12, WCAG 1.4.11 |
| 5 | M | "✗ Broken" in red reads as a failure | Reframe the tile as "Tamper detected ✓" (value "Caught at row 2,130"), in the ok color with an alarm icon, and explain in one line. | DL + PO | img/exec-fold-1440.png | R13, R8 |
| 6 | M | Missing headings on qc, tube and scorecard pages; H1→H3 skip | Add H2s: QC "Pick a plate", "Inside the plate", "Reference curve", "Flags". Scorecard: H2 "The 13 problems" before the cards. Tube: H2 "Play the tube's journey", "What the real check said". | DL | dom-audit.json `h` | WCAG 1.3.1, 2.4.6 |
| 7 | M | Radio/checkbox groups unnamed; range unlabeled | Wrap Observable Inputs in `<fieldset><legend>` (or set `role=radiogroup aria-labelledby`); give the range `aria-label="Your guess, percent"`. | DL | dom-audit.json `unlabeledInputs` | WCAG 1.3.1, 4.1.2 |
| 8 | M | No skip link | Add `<a class="skip-link" href="#quarto-document-content">Skip to content</a>` in `_banner.html`, visible on focus. | DL | dom-audit.json `skip:false` | WCAG 2.4.1 |
| 9 | M | Guess game spoils itself | Hide the "What this means" numbers and KPI tile 2 value until `revealed` (or move the game above the KPIs as a teaser), and keep `?reveal` for execs. | DL + AE | index.qmd `meaningBox` | R8 |
| 10 | M | Science wording: "stronger dilution"; duplicate "45% / 20% disagreement" vs CV | Use "a higher dilution (for example 1:1,000)". Write "the duplicate wells' CV was 53%, above the 20% limit". | AE | scorecard.qmd story(), qc.qmd valid-range box | R5 (correct expert terms) |
| 11 | M | Chart text 10-13 px, not zoom-friendly | Plot `fontSize: "15px"`, tick labels at least 14 px, facet labels shortened ("Vaccine, 60"). Re-check at 640 px. | DL | img/zoom200-full.png; smallText=264 | R1, R2, WCAG 1.4.4 |
| 12 | M | Idioms block non-native readers | Content pass with the R6 checklist: replace "by a wide margin", "behind the system's back", "drag it up", "made-up" and similar with literal words. | PO (+DL) | page text | R6, R4 |
| 13 | M | Top-of-page density (ADHD) | Fold the KPI notes into the `<details>`; leave title + value + one-line plain note. Link each glossary term once per page. | DL | img/exec-fold-1440.png | R8, R5 |
| 14 | m | Deuteranopia: ok/bad hues identical | Move `--ok`/`--bad` toward Okabe-Ito blue #0072B2 / vermillion #D55E00 (check 4.5:1 in both themes), or add a hatch to rejected plates. | DL | img/deut-qc.png | R11 |
| 15 | m | Status badge `aria-live` announces on every load | Remove `aria-live` from `.status-badge` (it is not a live update). | DL | _status.qmd | R8 |
| 16 | m | Label 19.7x as GMR; soften "cannot drag it up"; add "(95% CI)" | Copy edits in index.qmd. | AE | index.qmd kpis | R5 |
| 17 | m | Tables without caption/scope; raw-URL link text in glossary | Add `<caption>` and `scope="col"`; use the source title as link text. Replace the BioSpace job-ad citation. | DL + AE | dom-audit.json `tables` | WCAG 1.3.1, 2.4.4 |
| 18 | m | "QCflags" (missing space) in flag-table summary | `summary{display:inline-flex}` eats the space after the auto-linked "QC". Use `display:list-item` or a `gap`, or `&nbsp;` after the term. | DL | img/deut-qc.png | polish |
| 19 | m | Mixed colour/color spelling | Standardize on US English. | AE | glossary.json, qc.qmd axis | R6 |

---

## 4. Turning the overview into a scroll-driven "production story" for executives

Principle: the reader scrolls normally and the page reacts to them. Never scrolljack (R14). Every chapter must work as a static page with motion off.

1. **Five chapters, each one screen, each headed by its own one-sentence answer.** (1) *Verdict*: "On track: the vaccine worked and every planted problem was caught." (2) *The vaccine worked*: unit chart, 56 of 58 vs 0 of 60. (3) *Antibodies rose 16x and stayed high*: the GMT chart, D1 → D29 → D57. (4) *The lab threw out only the plates it should*: 11 of 13 accepted, both rejects planted. (5) *Tampering was detected*: tube SMP-00180's seal breaks at row 2,130, 13 of 13 caught, 0 false plate rejections. Each H2 is the takeaway, not a topic (R13, R8).
2. **Numbers count up once as they enter the viewport.** Use `IntersectionObserver` at threshold 0.5, run once, for at most 800 ms with ease-out, using `font-variant-numeric: tabular-nums` so the width does not jump. The final value is in the DOM from the start; the count-up only animates `textContent`. Screen readers get the real value through `aria-label` on the number, and the counting span is `aria-hidden` (R10).
3. **Sticky chart, stepping text ("scrollama" pattern) for chapters 2-3 only.** The chart pins while 2-3 short text steps scroll past: "Before the shot, both groups look the same" → "By Day 29 the vaccine group rises" → "By Day 57 it eases but stays high". Each step changes one thing (highlight, filter). Keep fades and transitions under 400 ms (R15). Step text has to be readable without the chart.
4. **Reduced-motion fallback = same story, no movement.** Under `prefers-reduced-motion: reduce`, numbers render final immediately, sticky sections become normal stacked figures (each step shows its own small static chart or a highlighted state), and nothing pins. This also applies when JS fails and in forced colors. The CSS already kills animations globally; add a JS `matchMedia` check so counters and observers are never started (WCAG 2.3.3, R2 "avoid auto-moving text").
5. **Progress and escape hatches.** A thin chapter rail (5 labeled dots, keyboard-focusable anchor links) shows where you are. Add a "Skip the story: show all results" link at the top that jumps to a static summary table. Each chapter has an anchor so an exec can share "#tampering".
6. **The exec reader gets no gate.** Keep the guess game, but put it *after* the verdict and the reveal, as optional "Test your intuition", or open the page with `?reveal` as the default for the story. Executives should never have to click to see a result (R13).
7. **Chapter end-cards with one number and one "so what".** For example, "0 of 13 plates rejected without cause: QC is not crying wolf." Large type (≥ 2.5 rem), one sentence, links to the deep page (Lab QC, Follow one tube, Scorecard) for P8-type readers.
8. **Test it like the panel did.** Run QA screenshots at 1280x720 (fold), 640 px (200% zoom), forced-colors and reduced-motion for every chapter. Pass criterion: a cold reader states the verdict after 5 seconds.

## 5. What a 30-second reader must get, even if they stop scrolling

These must all be visible in the first viewport at 1280x720, as text (not animation-dependent), in this order:

1. **Verdict:** "On track." The vaccine worked in this SYNTHETIC trial, and the data pipeline caught every planted problem.
2. **The vaccine number:** 56 of 58 vaccinated volunteers responded (96%) vs 0 of 60 on placebo, by Day 29.
3. **The trust number:** 13 of 13 planted problems caught, with 0 plates rejected without cause (no false alarms).
4. **The integrity number:** a deliberate tamper was detected at the exact row edited.
5. **The caveat, once, small:** SYNTHETIC demo data, not a validated system. Show it once in the banner, not four times above the fold.

Everything else (GMT/GMFR, CIs, plate detail, hashes, run metadata) is chapter 2 onward.
