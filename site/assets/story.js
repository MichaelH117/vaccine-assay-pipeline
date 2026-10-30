// Overview "production story": chapter reveals, count-up numbers, chapter rail, and the global "Pause motion" control.
// No scroll-jacking: the page scrolls normally and only reacts. Every number is already in the HTML; motion only
// animates it. Under prefers-reduced-motion (or after "Pause motion") nothing moves and everything shows at once.
(function () {
  "use strict";
  const root = document.documentElement;
  const rm = window.matchMedia("(prefers-reduced-motion: reduce)");
  let paused = false;
  try { paused = localStorage.getItem("story-paused") === "1"; } catch (e) { /* storage blocked: default on */ }
  if (paused) root.classList.add("motion-paused");
  const motionOK = () => !rm.matches && !paused;
  const counters = [];

  function finishAll() {
    document.querySelectorAll(".chapter").forEach((c) => c.classList.add("in"));
    counters.forEach((c) => c.finish());
  }
  function setPaused(p) {
    paused = p;
    root.classList.toggle("motion-paused", p);
    root.classList.toggle("story-motion", motionOK());
    try { localStorage.setItem("story-paused", p ? "1" : "0"); } catch (e) { /* ignore */ }
    syncButtons();
    if (!motionOK()) finishAll();
    window.dispatchEvent(new CustomEvent("storymotion", { detail: { paused: p } }));
  }
  function syncButtons() {
    document.querySelectorAll("[data-motion-toggle]").forEach((b) => {
      if (rm.matches) { b.disabled = true; b.textContent = "Motion off (system setting)"; b.setAttribute("aria-pressed", "true"); return; }
      b.setAttribute("aria-pressed", String(paused));
      b.textContent = paused ? "▶ Turn motion on" : "❚❚ Pause motion";
    });
  }

  // Count-up: the final value stays in the DOM for screen readers; only an aria-hidden copy animates (< 800 ms).
  function makeCounter(el) {
    const final = el.textContent.trim();
    const m = final.match(/^([^0-9]*)([0-9][0-9,]*\.?[0-9]*)(.*)$/);
    if (!m) return;
    const target = parseFloat(m[2].replace(/,/g, ""));
    const dec = (m[2].split(".")[1] || "").length;
    const comma = m[2].includes(",");
    el.textContent = "";
    const sr = document.createElement("span"); sr.className = "visually-hidden"; sr.textContent = final;
    const vis = document.createElement("span"); vis.setAttribute("aria-hidden", "true"); vis.className = "cu-vis"; vis.textContent = final;
    el.append(sr, vis);
    const fmt = (v) => m[1] + (comma ? v.toLocaleString("en-US", { minimumFractionDigits: dec, maximumFractionDigits: dec }) : v.toFixed(dec)) + m[3];
    let done = false, raf = 0;
    const c = {
      finish() { done = true; cancelAnimationFrame(raf); vis.textContent = final; },
      run() {
        if (done) return; done = true;
        if (!motionOK() || target === 0) { vis.textContent = final; return; }
        const t0 = performance.now(), D = 700;
        const step = (now) => {
          const k = Math.min(1, (now - t0) / D), e = 1 - Math.pow(1 - k, 3);
          vis.textContent = fmt(dec ? target * e : Math.floor(target * e));
          if (k < 1) raf = requestAnimationFrame(step); else vis.textContent = final;
        };
        raf = requestAnimationFrame(step);
      }
    };
    counters.push(c);
    return [el, c];
  }

  function init() {
    if (!document.querySelector(".story")) return;
    root.classList.add("story-js");
    if (motionOK()) root.classList.add("story-motion");
    syncButtons();
    document.querySelectorAll("[data-motion-toggle]").forEach((b) => b.addEventListener("click", () => setPaused(!paused)));
    rm.addEventListener?.("change", () => { root.classList.toggle("story-motion", motionOK()); syncButtons(); if (!motionOK()) finishAll(); });

    const chapters = [...document.querySelectorAll(".chapter")];
    const pairs = [...document.querySelectorAll(".cu")].map(makeCounter).filter(Boolean);
    if (!("IntersectionObserver" in window) || !motionOK()) { finishAll(); }
    else {
      const rev = new IntersectionObserver((es) => es.forEach((e) => { if (e.isIntersecting) { e.target.classList.add("in"); rev.unobserve(e.target); } }),
        { rootMargin: "0px 0px -8% 0px", threshold: 0.02 });
      chapters.forEach((c) => rev.observe(c));
      const cio = new IntersectionObserver((es) => es.forEach((e) => {
        if (e.isIntersecting) { const p = pairs.find(([el]) => el === e.target); if (p) p[1].run(); cio.unobserve(e.target); }
      }), { threshold: 0.6 });
      pairs.forEach(([el]) => cio.observe(el));
      // A chapter opened by a link (#ch-tamper) shows at once.
      const open = () => { const t = location.hash && document.querySelector(location.hash); if (t) { (t.closest(".chapter") || t).classList.add("in"); } };
      window.addEventListener("hashchange", open); open();
    }

    // Chapter rail: mark the chapter in the middle of the screen.
    const links = [...document.querySelectorAll(".rail a")];
    const targets = links.map((a) => document.querySelector(a.getAttribute("href"))).filter(Boolean);
    if ("IntersectionObserver" in window && targets.length) {
      const rio = new IntersectionObserver((es) => es.forEach((e) => {
        if (!e.isIntersecting) return;
        links.forEach((a) => a.toggleAttribute("aria-current", a.getAttribute("href") === "#" + e.target.id));
        links.forEach((a) => { if (a.hasAttribute("aria-current")) a.setAttribute("aria-current", "location"); });
      }), { rootMargin: "-45% 0px -50% 0px" });
      targets.forEach((t) => rio.observe(t));
    }
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})();
