// Shared behaviour: status badge + glossary tooltips (hover AND keyboard focus, Esc to dismiss; WCAG 1.4.13).
(function () {
  "use strict";
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  // ---- status badge (every page) -------------------------------------------------------------
  fetch("data/meta.json").then((r) => r.json()).then((m) => {
    document.querySelectorAll(".status-badge").forEach((el) => {
      const t = m.tests, d = m.dbt;
      const testsOk = t.failed === 0 && t.error === 0;
      const dbtOk = d.failed === 0;
      // One compact line (fix 2 / 13): the SYNTHETIC caveat lives in the banner, so it is not repeated here.
      el.innerHTML =
        `<span class="chip ${testsOk && dbtOk ? "ok" : "bad"}">${testsOk && dbtOk ? "&#10003; All automated checks passed" : "&#10007; Some automated checks failed"}</span>` +
        `<span class="chip">Data as of <b>${esc(m.run_at_utc.replace("T", " ").slice(0, 16))} UTC</b></span>` +
        `<details class="run-details"><summary>Run details</summary><span>pytest ${t.passed} of ${t.passed + t.failed + t.error} passed (${esc(t.date)}) · ` +
        `<a class="term" href="glossary.html#dbt" data-term="dbt">dbt</a>&nbsp;${d.passed} of ${d.nodes} passed · seed ${esc(m.seed)} · rules ${esc(m.rule_version)} · build ${esc(m.git_sha)}</span></details>`;
      wire(el);
    });
  }).catch(() => {
    document.querySelectorAll(".status-badge").forEach((el) => {
      el.innerHTML = `<span class="chip warn">&#9888; Run status could not be loaded</span>`;
    });
  });

  // ---- glossary tooltips ---------------------------------------------------------------------
  let G = {};
  const tip = document.createElement("div");
  tip.id = "gloss-tip"; tip.setAttribute("role", "tooltip"); tip.hidden = true;
  document.addEventListener("DOMContentLoaded", () => document.body.appendChild(tip));
  let current = null;

  function idOf(a) {
    if (a.dataset.term) return a.dataset.term;
    const h = (a.getAttribute("href") || "").split("#")[1];
    return h || null;
  }
  function show(a) {
    const g = G[idOf(a)];
    if (!g) return;
    current = a;
    tip.innerHTML = `<b>${esc(g.term)}${g.full && g.full !== g.term ? " · " + esc(g.full) : ""}</b>${esc(g.def)}<br><span style="opacity:.8">Click for the glossary entry.</span>`;
    tip.hidden = false;
    a.setAttribute("aria-describedby", "gloss-tip");
    const r = a.getBoundingClientRect();
    const w = Math.min(320, window.innerWidth - 24);
    tip.style.maxWidth = w + "px";
    let left = window.scrollX + r.left;
    left = Math.max(window.scrollX + 12, Math.min(left, window.scrollX + window.innerWidth - w - 12));
    tip.style.left = left + "px";
    tip.style.top = window.scrollY + r.bottom + 8 + "px";
  }
  function hide() {
    if (current) current.removeAttribute("aria-describedby");
    current = null; tip.hidden = true;
  }
  function wire(root) {
    root.querySelectorAll("a.term:not([data-wired])").forEach((a) => {
      a.dataset.wired = "1";
      a.addEventListener("mouseenter", () => show(a));
      a.addEventListener("mouseleave", (e) => { if (!tip.contains(e.relatedTarget)) hide(); });
      a.addEventListener("focus", () => show(a));
      a.addEventListener("blur", hide);
    });
  }
  tip.addEventListener("mouseleave", hide);

  // Every acronym in page text links to its glossary entry (skips code, links, headings' anchors, controls, SVG).
  const ACR = { "ALCOA+": "alcoa", LIMS: "lims", ELISA: "elisa", GMFR: "gmfr", GMT: "gmt", LLOQ: "lloq", ULOQ: "uloq",
    "4PL": "4pl", QC: "qc", CV: "cv", OD: "od", CI: "ci", GCLP: "gclp", GxP: "gxp", SOP: "sop", "AU/mL": "au-ml" };
  const RX = /(?<![\w\/-])(ALCOA\+|LIMS|ELISA|GMFR|GMT|LLOQ|ULOQ|4PL|QC|CV|OD|CI|GCLP|GxP|SOP|AU\/mL)(?![\w-])/g;
  const RT = new RegExp(RX.source);
  const SKIP = "a,code,pre,script,style,svg,button,label,select,option,input,textarea,nav,.navbar,.status-badge,.verify-out,.hash,#gloss-tip,.gloss-list dt,title,figcaption svg,.sidebar,.term-dup,.rail,.big,.ec-num,.cu,.skip-link";
  function linkify() {
    const main = document.querySelector("main") || document.body;
    const walker = document.createTreeWalker(main, NodeFilter.SHOW_TEXT, {
      acceptNode: (n) => (!n.nodeValue || !RT.test(n.nodeValue) || n.parentElement.closest(SKIP)) ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT
    });
    const nodes = []; let n; while ((n = walker.nextNode())) nodes.push(n);
    for (const t of nodes) {
      const frag = document.createDocumentFragment(); let last = 0; const v = t.nodeValue;
      v.replace(RX, (m, g, off) => {
        frag.append(v.slice(last, off));
        const a = document.createElement("a"); a.className = "term"; a.href = "glossary.html#" + ACR[g]; a.textContent = g;
        frag.append(a); last = off + m.length; return m;
      });
      frag.append(v.slice(last)); t.replaceWith(frag);
    }
  }
  // Link each glossary term once per page (fix 13): the first occurrence in reading order keeps the link, later
  // ones become plain text. Reversible, because OJS cells re-render.
  function dedupe() {
    const main = document.querySelector("main") || document.body;
    const seen = new Set();
    main.querySelectorAll("a.term, span.term-dup").forEach((el) => {
      const id = el.tagName === "A" ? idOf(el) : el.dataset.term;
      if (!id || el.closest(".status-badge,.gloss-list")) return;
      if (!seen.has(id)) {
        seen.add(id);
        if (el.tagName === "SPAN") { const a = document.createElement("a"); a.className = "term"; a.href = el.dataset.href; a.textContent = el.textContent; el.replaceWith(a); }
      } else if (el.tagName === "A") {
        const sp = document.createElement("span"); sp.className = "term-dup"; sp.dataset.term = id; sp.dataset.href = el.getAttribute("href");
        sp.textContent = el.textContent; el.replaceWith(sp);
      }
    });
  }
  // Accessible names for Observable Inputs (fix 7) and table semantics (fix 17).
  let uid = 0;
  function enhance() {
    document.querySelectorAll('form[class*="oi-"]:not([data-a11y])').forEach((f) => {
      f.dataset.a11y = "1";
      const lab = f.querySelector(":scope > label");
      const radios = f.querySelectorAll("input[type=radio]"), boxes = f.querySelectorAll("input[type=checkbox]");
      if (lab && (radios.length || boxes.length > 1)) {
        lab.id = lab.id || "oi-lab-" + (++uid);
        f.setAttribute("role", radios.length ? "radiogroup" : "group");
        f.setAttribute("aria-labelledby", lab.id);
      }
      f.querySelectorAll("input[type=range]").forEach((r) => {
        if (!r.getAttribute("aria-label")) r.setAttribute("aria-label", (lab ? lab.textContent.trim() : "Value") + " (slider)");
      });
    });
    document.querySelectorAll("table.table-x, main table").forEach((t) => {
      t.querySelectorAll("thead th:not([scope])").forEach((th) => th.setAttribute("scope", "col"));
      if (!t.querySelector("caption")) {
        const sum = t.closest("details")?.querySelector("summary");
        const c = document.createElement("caption"); c.className = "visually-hidden";
        c.textContent = sum ? sum.textContent.replace(/\s*·\s*view as table/i, "").trim() : "Data table";
        t.prepend(c);
      }
    });
  }
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") hide(); });

  fetch("data/glossary.json").then((r) => r.json()).then((j) => {
    j.terms.forEach((t) => { G[t.id] = t; });
    linkify(); dedupe(); enhance(); wire(document);
    // OJS cells render after load: link and wire new text as it appears.
    let pending = false;
    new MutationObserver(() => {
      if (pending) return; pending = true;
      requestAnimationFrame(() => { pending = false; linkify(); dedupe(); enhance(); wire(document); });
    }).observe(document.body, { childList: true, subtree: true });
  });
})();
