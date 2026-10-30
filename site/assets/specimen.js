// SPECIMEN behaviour, on every page:
//  1. the "living specimen" wallpaper: a fixed, full-viewport layer behind everything. Soft cell-like droplets merge and
//     part very slowly (a metaball field rendered at about 1/10 resolution and upscaled with blur), with faint plate
//     grids, registration marks and lab-label callouts drifting over it. Content floats above it on paper panels.
//  2. a scroll-progress strip of plate wells that fill as you read (reacts to scrolling only).
// Motion rules (WCAG 2.2.2, 2.3.1): every form takes 20-90 s to cross or change shape, on sine curves; colour changes
// are slow cross-fades (no flashing); a "Pause motion" button on every page; prefers-reduced-motion draws one still
// frame; it stops in a background tab; at most 30 frames a second. Contrast against the paper stays about 6-12%.
(function () {
  "use strict";
  const root = document.documentElement;
  const rm = window.matchMedia("(prefers-reduced-motion: reduce)");
  const KEY = "story-paused";                      // shared with story.js
  const isPaused = () => root.classList.contains("motion-paused");
  const motionOK = () => !rm.matches && !isPaused();
  const TAU = Math.PI * 2;

  // ---- pause control (story.js owns it on the overview; this wires it everywhere else) -------------------------
  function wireToggles() {
    if (root.classList.contains("story-js")) return;   // story.js already wired every [data-motion-toggle]
    try { if (localStorage.getItem(KEY) === "1") root.classList.add("motion-paused"); } catch (e) { /* storage blocked */ }
    const sync = () => document.querySelectorAll("[data-motion-toggle]").forEach((b) => {
      if (rm.matches) { b.disabled = true; PHset(b, "minus", "Motion off (system setting)"); b.setAttribute("aria-pressed", "true"); return; }
      b.disabled = false; b.setAttribute("aria-pressed", String(isPaused()));
      PHset(b, isPaused() ? "play" : "pause", isPaused() ? "Turn motion on" : "Pause motion");
    });
    document.querySelectorAll("[data-motion-toggle]").forEach((b) => b.addEventListener("click", () => {
      const p = !isPaused();
      root.classList.toggle("motion-paused", p);
      try { localStorage.setItem(KEY, p ? "1" : "0"); } catch (e) { /* ignore */ }
      sync();
      window.dispatchEvent(new CustomEvent("storymotion", { detail: { paused: p } }));
    }));
    rm.addEventListener?.("change", sync);
    sync();
  }

  // ---- well progress ---------------------------------------------------------------------------------------------
  function wellProgress() {
    const bar = document.createElement("div");
    bar.className = "well-progress"; bar.setAttribute("aria-hidden", "true");
    document.body.appendChild(bar);
    let n = 0, wells = [], last = -1, raf = 0;
    const build = () => {
      const want = window.innerWidth >= 900 ? 96 : 48;
      if (want === n) return;
      n = want; bar.innerHTML = ""; wells = [];
      for (let i = 0; i < n; i++) { const w = document.createElement("i"); bar.appendChild(w); wells.push(w); }
      last = -1;
    };
    const update = () => {
      raf = 0;
      const max = document.documentElement.scrollHeight - window.innerHeight;
      const filled = Math.round((max > 0 ? Math.min(1, Math.max(0, window.scrollY / max)) : 1) * n);
      if (filled === last) return;
      wells.forEach((w, i) => w.classList.toggle("on", i < filled));
      last = filled;
    };
    build(); update();
    window.addEventListener("scroll", () => { if (!raf) raf = requestAnimationFrame(update); }, { passive: true });
    window.addEventListener("resize", () => { build(); update(); });
  }

  // ---- the living specimen wallpaper --------------------------------------------------------------------------
  function wallpaper() {
    const host = document.createElement("div");
    host.className = "living-specimen"; host.setAttribute("aria-hidden", "true");
    const blobC = document.createElement("canvas"); blobC.className = "ls-blobs";
    const lineC = document.createElement("canvas"); lineC.className = "ls-lines";
    host.append(blobC, lineC);
    document.body.prepend(host);
    const bctx = blobC.getContext("2d"), lctx = lineC.getContext("2d");

    // seeded random: the still frame is identical on every visit
    let seed = 42;
    const rnd = () => { seed = (seed * 16807) % 2147483647; return (seed - 1) / 2147483646; };
    const sm = (a, b, x) => { const t = Math.min(1, Math.max(0, (x - a) / (b - a))); return t * t * (3 - 2 * t); };
    const hex = (h) => { h = h.replace("#", ""); return [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16)); };

    // droplets: each centre follows two slow sines (periods 40-90 s); radius breathes over 20-40 s
    const drops = Array.from({ length: 9 }, (_, i) => ({
      cx: 0.1 + 0.8 * rnd(), cy: 0.1 + 0.8 * rnd(), ax: 0.12 + 0.18 * rnd(), ay: 0.1 + 0.18 * rnd(),
      px: 40 + 50 * rnd(), py: 45 + 45 * rnd(), ph: rnd() * TAU, r: 0.07 + 0.07 * rnd(), pr: 20 + 20 * rnd(),
      tint: i === 3 ? "amber" : i === 6 ? "rust" : "teal"
    }));
    // drifting line motifs (vector layer)
    const LABELS = ["B07", "OD 3.212", "PLATE-004", "row 2,130", "SMP-00180", "seed 42", "A01", "4PL", "D29"];
    const motifs = [];
    const add = (type, n, extra) => { for (let i = 0; i < n; i++) motifs.push({ type, x: rnd(), y: rnd(), ax: 0.04 + 0.05 * rnd(),
      ay: 0.03 + 0.05 * rnd(), p: 50 + 40 * rnd(), ph: rnd() * TAU, s: rnd(), rot: (rnd() - 0.5) * 0.25, depth: 0.3 + 0.7 * rnd(), ...(extra ? extra(i) : {}) }); };
    add("plate", 2); add("reg", 6); add("callout", 6, (i) => ({ text: LABELS[i % LABELS.length] }));
    add("type", 2, (i) => ({ text: ["96", "A01"][i] })); add("chain", 2);

    // mood per chapter (overview): weights cross-fade over a few seconds
    const MOODS = {
      calm: { plate: 0.5, callout: 0.6, chain: 0, amber: 0, rust: 0 },
      plate: { plate: 1, callout: 0.7, chain: 0, amber: 1, rust: 0 },
      ledger: { plate: 0.4, callout: 1, chain: 0, amber: 0.3, rust: 0 },
      chain: { plate: 0.3, callout: 0.8, chain: 1, amber: 0, rust: 1 }
    };
    let target = MOODS.calm; const mood = { ...MOODS.calm };

    let W = 0, H = 0, bw = 0, bh = 0, img = null, col = null;
    const readColors = () => {
      const cs = getComputedStyle(root);
      const g = (n, d) => (cs.getPropertyValue(n).trim() || d);
      col = { paper: hex(g("--bg", "#F5F2EB")), teal: hex(g("--ls-teal", "#0F5E6B")), amber: hex(g("--amber", "#E3B23C")),
        rust: hex(g("--ls-rust", "#A4471A")), ink: g("--ls-line", "#0F5E6B"), strength: parseFloat(g("--ls-strength", ".10")) };
    };
    const size = () => {
      W = window.innerWidth; H = window.innerHeight;
      bw = Math.max(48, Math.round(W / 10)); bh = Math.max(32, Math.round(H / 10));
      blobC.width = bw; blobC.height = bh; img = bctx.createImageData(bw, bh);
      lineC.width = W; lineC.height = H;                  // device pixel ratio 1: soft lines are fine and cheap
    };

    function drawBlobs(t) {
      const d = img.data, P = col.paper, S = col.strength;
      const pos = drops.map((b) => [
        (b.cx + b.ax * Math.sin(TAU * t / b.px + b.ph)) * bw,
        (b.cy + b.ay * Math.sin(TAU * t / b.py + b.ph * 1.7)) * bh,
        (b.r * (1 + 0.18 * Math.sin(TAU * t / b.pr + b.ph))) * Math.max(bw, bh), b.tint]);
      // breathing teal: a slow 30 s swell of +-15% in strength
      const breathe = 1 + 0.15 * Math.sin(TAU * t / 30);
      for (let y = 0, k = 0; y < bh; y++) for (let x = 0; x < bw; x++, k += 4) {
        let f = 0, fa = 0, fr = 0;
        for (const [px, py, r, tint] of pos) {
          const dx = x - px, dy = y - py, v = (r * r) / (dx * dx + dy * dy + 1);
          f += v; if (tint === "amber") fa += v; else if (tint === "rust") fr += v;
        }
        const body = sm(0.55, 1.15, f);                    // the droplet's soft interior
        const rim = sm(0.75, 1.0, f) * (1 - sm(1.0, 1.5, f)); // a membrane band where droplets meet
        let a = (0.45 * body + 0.9 * rim) * S * breathe;
        const wa = mood.amber * Math.min(1, fa / (f + 1e-6)), wr = mood.rust * Math.min(1, fr / (f + 1e-6));
        const wt = Math.max(0, 1 - wa - wr);
        const cr = col.teal[0] * wt + col.amber[0] * wa + col.rust[0] * wr;
        const cg = col.teal[1] * wt + col.amber[1] * wa + col.rust[1] * wr;
        const cb = col.teal[2] * wt + col.amber[2] * wa + col.rust[2] * wr;
        a = Math.min(a, S * 1.2);
        d[k] = P[0] + (cr - P[0]) * a; d[k + 1] = P[1] + (cg - P[1]) * a; d[k + 2] = P[2] + (cb - P[2]) * a; d[k + 3] = 255;
      }
      bctx.putImageData(img, 0, 0);
    }

    function drawLines(t) {
      lctx.clearRect(0, 0, W, H);
      lctx.strokeStyle = col.ink; lctx.fillStyle = col.ink; lctx.lineWidth = 1;
      const S = col.strength;
      for (const m of motifs) {
        const w = m.type === "plate" ? mood.plate : m.type === "callout" ? mood.callout : m.type === "chain" ? mood.chain : 1;
        if (w < 0.02) continue;
        const x = (m.x + m.ax * Math.sin(TAU * t / m.p + m.ph)) * W;
        const y = (m.y + m.ay * Math.cos(TAU * t / (m.p * 1.3) + m.ph)) * H;
        lctx.save(); lctx.translate(x, y); lctx.rotate(m.rot + 0.04 * Math.sin(TAU * t / (m.p * 2) + m.ph));
        lctx.globalAlpha = S * w * (0.6 + 0.4 * m.depth) * 1.6;
        if (m.type === "plate") {                        // a 96-well plate, 8 x 12
          const g = 16 + 14 * m.depth;
          lctx.strokeRect(-g * 0.8, -g * 0.8, g * 12 + g * 0.6, g * 8 + g * 0.6);
          for (let r = 0; r < 8; r++) for (let c = 0; c < 12; c++) {
            lctx.beginPath(); lctx.arc(c * g + g / 2 - g * 0.5, r * g + g / 2 - g * 0.5, g * 0.34, 0, TAU); lctx.stroke();
          }
        } else if (m.type === "reg") {                   // registration mark
          const R = 9 + 10 * m.s;
          lctx.beginPath(); lctx.arc(0, 0, R, 0, TAU); lctx.moveTo(-R * 1.8, 0); lctx.lineTo(R * 1.8, 0); lctx.moveTo(0, -R * 1.8); lctx.lineTo(0, R * 1.8); lctx.stroke();
        } else if (m.type === "callout") {               // lab-label callout: dot, leader, label
          lctx.beginPath(); lctx.arc(0, 0, 3, 0, TAU); lctx.fill();
          lctx.beginPath(); lctx.moveTo(0, 0); lctx.lineTo(28, -28); lctx.lineTo(96, -28); lctx.stroke();
          lctx.font = "500 12px 'IBM Plex Mono', monospace"; lctx.fillText(m.text, 32, -33);
        } else if (m.type === "type") {                  // oversized type fragment, outline only
          lctx.globalAlpha *= 0.55; lctx.font = `600 ${Math.round(H * 0.42)}px Fraunces, Georgia, serif`;
          lctx.strokeText(m.text, -H * 0.2, H * 0.15);
        } else if (m.type === "chain") {                 // interlocked links: the audit chain
          for (let i = 0; i < 4; i++) { const rr = 14; lctx.beginPath(); lctx.roundRect(i * 44 - 30, i % 2 ? -10 : -16, 58, i % 2 ? 20 : 32, rr); lctx.stroke(); }
        }
        lctx.restore();
      }
      // one slow scan band, top to bottom every 40 s, barely there
      const yb = ((t / 40) % 1) * (H + 200) - 100;
      const gr = lctx.createLinearGradient(0, yb - 80, 0, yb + 80);
      gr.addColorStop(0, "rgba(0,0,0,0)"); gr.addColorStop(0.5, col.ink); gr.addColorStop(1, "rgba(0,0,0,0)");
      lctx.globalAlpha = S * 0.25; lctx.fillStyle = gr; lctx.fillRect(0, yb - 80, W, 160); lctx.globalAlpha = 1;
    }

    const STILL_T = 23;   // the reduced-motion still: a moment where droplets are just touching
    let running = false, raf = 0, t = STILL_T, lastNow = 0, lastFrame = 0;
    const render = () => {
      for (const k in mood) mood[k] += (target[k] - mood[k]) * (running ? 0.03 : 1);
      drawBlobs(t); drawLines(t);
    };
    const frame = (now) => {
      raf = 0; if (!running) return;
      if (now - lastFrame >= 1000 / 30) {               // capped at 30 fps
        t += Math.min(0.1, (now - (lastNow || now)) / 1000); lastNow = now; lastFrame = now; render();
      }
      raf = requestAnimationFrame(frame);
    };
    const sync = () => {
      const want = motionOK() && !document.hidden;
      if (want && !running) { running = true; lastNow = 0; raf = requestAnimationFrame(frame); }
      else if (!want && running) { running = false; if (raf) cancelAnimationFrame(raf); raf = 0; }
      if (!running) { if (rm.matches) t = STILL_T; render(); }
    };
    // chapter moods (overview only): the chapter nearest the middle of the screen sets the target
    const moodEls = [...document.querySelectorAll("[data-mood]")];
    if (moodEls.length && "IntersectionObserver" in window) {
      const io = new IntersectionObserver((es) => es.forEach((e) => {
        if (e.isIntersecting) { target = MOODS[e.target.dataset.mood] || MOODS.calm; if (!running) render(); }
      }), { rootMargin: "-45% 0px -50% 0px" });
      moodEls.forEach((el) => io.observe(el));
    }
    readColors(); size();
    document.addEventListener("visibilitychange", sync);
    window.addEventListener("storymotion", sync);
    rm.addEventListener?.("change", sync);
    window.addEventListener("resize", () => { size(); if (!running) render(); });
    // Quarto's light/dark toggle swaps stylesheets: re-read the palette
    new MutationObserver(() => { readColors(); if (!running) render(); }).observe(document.body, { attributes: true, attributeFilter: ["class"] });
    sync();
  }

  // A real loop, once one is approved and dropped into the hero slot, follows the same rules.
  function slotVideos() {
    document.querySelectorAll(".micrograph-slot video").forEach((v) => {
      const sync = () => { if (motionOK() && !document.hidden) v.play().catch(() => {}); else v.pause(); };
      window.addEventListener("storymotion", sync); rm.addEventListener?.("change", sync);
      document.addEventListener("visibilitychange", sync); sync();
    });
  }

  function init() {
    wireToggles();
    slotVideos();
    wallpaper();
    wellProgress();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})();
