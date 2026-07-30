/* The five named brain rhythms, taken out of one real recording.
 *
 * WHAT IS REAL HERE. Every trace is the same channel of the same person, one
 * minute apart, eyes closed and eyes open: PhysioNet's EEG Motor Movement and
 * Imagery Database, subject 1, ODC-BY. Nothing is simulated and no band comes
 * from a different source than any other, which is the only way the comparison
 * between them means anything.
 *
 * HOW THE BANDS WERE SEPARATED. A fourth order Butterworth band pass applied
 * forwards and then backwards, so the filter contributes no phase shift. A one
 * directional filter delays each band by a different amount and the stack then
 * lies about when things happen relative to each other.
 *
 * WHAT TO BE CAREFUL OF. Delta looks enormous with the eyes open. That is very
 * largely eye movement and blinks, not cortical delta, and the page says so
 * rather than letting a reader conclude that opening your eyes puts you into
 * deep sleep.
 */
const NS = "http://www.w3.org/2000/svg";

const BAND_COLOR = {
  delta: "#6C5BE0", theta: "#3E96F0", alpha: "#3FE3B0",
  beta: "#FFB24D", gamma: "#FF5C7A",
};

export async function mountWaves(root) {
  const stack = root.querySelector("[data-stack]");
  const bars = root.querySelector("[data-bars]");
  const tabs = root.querySelector("[data-state]");
  const head = root.querySelector("[data-head]");
  if (!stack) return;

  const all = await fetch("data/signals.json").then((r) => r.json());
  const sig = all.signals["eeg-bands"];
  if (!sig) return;

  let state = "closed";

  function draw() {
    const st = sig.states[state];
    const W = 720, ROW = 62, PAD = 8;
    const H = sig.bands.length * ROW + PAD * 2;

    /* One shared vertical scale across all five bands, so the picture is
       honest about how much bigger alpha is than gamma. Scaling each band to
       its own row would make them all look the same size, which is precisely
       the thing worth seeing here. */
    let amp = 0;
    sig.bands.forEach((b) => {
      st.traces[b.name].forEach((v) => { amp = Math.max(amp, Math.abs(v)); });
    });

    let s = `<svg viewBox="0 0 ${W} ${H}" width="100%" class="wsvg" ` +
      `role="img" aria-label="Five EEG bands from one recording">`;
    sig.bands.forEach((b, i) => {
      const y0 = PAD + i * ROW + ROW / 2;
      const tr = st.traces[b.name];
      const dx = W / (tr.length - 1);
      let d = "";
      for (let k = 0; k < tr.length; k++) {
        const y = y0 - (tr[k] / amp) * (ROW * 0.44);
        d += `${k ? "L" : "M"} ${(k * dx).toFixed(1)} ${y.toFixed(1)} `;
      }
      s += `<line x1="0" x2="${W}" y1="${y0}" y2="${y0}" class="wbase"/>` +
        `<path d="${d}" stroke="${BAND_COLOR[b.name]}" class="wline"/>`;
    });
    s += `</svg>`;
    stack.innerHTML = s;

    /* The labels sit outside the SVG so they scale with the page's own type
       rather than with the drawing. */
    const labs = root.querySelector("[data-labels]");
    if (labs) {
      labs.innerHTML = sig.bands.map((b) =>
        `<div class="wrow"><s style="background:${BAND_COLOR[b.name]}"></s>` +
        `<b>${b.name}</b><u>${b.low_Hz} to ${b.high_Hz} Hz</u>` +
        `<em>${st.share[b.name]}%</em></div>`).join("");
    }

    if (bars) {
      const max = Math.max(...Object.values(sig.states.closed.share),
                           ...Object.values(sig.states.open.share));
      bars.innerHTML = sig.bands.map((b) => {
        const c = sig.states.closed.share[b.name];
        const o = sig.states.open.share[b.name];
        return `<div class="bgrp"><span class="bname">${b.name}</span>` +
          `<div class="btrack"><i style="width:${100 * c / max}%;` +
          `background:${BAND_COLOR[b.name]}"></i>` +
          `<span>${c}% closed</span></div>` +
          `<div class="btrack o"><i style="width:${100 * o / max}%;` +
          `background:${BAND_COLOR[b.name]}"></i>` +
          `<span>${o}% open</span></div></div>`;
      }).join("");
    }

    if (head) {
      head.innerHTML =
        `Eyes <b>${state}</b>, channel ${st.channel}, ${st.seconds} seconds at ` +
        `${st.fs} Hz. Alpha is <b>${st.share.alpha}%</b> of the total power ` +
        `here, against ${sig.states[state === "closed" ? "open" : "closed"]
          .share.alpha}% with the eyes ` +
        `${state === "closed" ? "open" : "closed"}.`;
    }
  }

  if (tabs) {
    tabs.innerHTML = [["closed", "Eyes closed"], ["open", "Eyes open"]]
      .map(([k, l], i) => `<button type="button" role="tab" data-st="${k}" ` +
        `aria-selected="${i === 0}">${l}</button>`).join("");
    tabs.addEventListener("click", (e) => {
      const b = e.target.closest("[data-st]");
      if (!b) return;
      state = b.dataset.st;
      tabs.querySelectorAll("[data-st]").forEach((x) =>
        x.setAttribute("aria-selected", String(x === b)));
      draw();
    });
  }

  draw();
  return { draw, sig };
}
