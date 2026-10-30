// Inline Phosphor-style icons from the sprite in _banner.html. PH("check") returns an <svg> node; PHs("check") the HTML string.
// Icons are always aria-hidden: the word next to them carries the meaning.
(function () {
  "use strict";
  const s = (name) => `<svg class="ph ph-${name}" aria-hidden="true" focusable="false"><use href="#ph-${name}"/></svg>`;
  window.PHs = s;
  window.PH = (name) => { const t = document.createElement("template"); t.innerHTML = s(name); return t.content.firstChild; };
  // Set a button to icon + label without losing the icon (used by play/pause controls).
  window.PHset = (el, name, label) => { el.innerHTML = s(name) + "<span>" + label + "</span>"; };
})();
