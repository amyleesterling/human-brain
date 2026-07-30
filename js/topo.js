/* Where on the head each rhythm actually sits.
 *
 * WHAT IS REAL HERE. Sixty four electrodes of one real recording, each one's
 * share of its own power in each band, so a noisy site cannot dominate every
 * map. Electrode positions are the standard 10-05 template, which is a generic
 * head and not this person's, so what is real is the pattern across sites and
 * not the millimetres.
 *
 * WHAT THIS IS NOT. It is not source localisation. A scalp electrode reads a
 * blurred sum of everything under it, spread out by the skull, so a hot spot at
 * the back of the head means the signal is strongest there on the scalp and not
 * that a patch of cortex directly beneath it is the generator. That is why
 * these are drawn as heads and not painted onto the cortical surface, which
 * would claim an inverse solution nobody here computed.
 *
 * THE INTERPOLATION between electrodes is inverse distance weighting, which is
 * a smooth guess and nothing more. The electrodes are drawn on top so you can
 * always see where the measurements actually were.
 */
const RAMP = [
  [8, 12, 20], [26, 48, 92], [40, 110, 180],
  [70, 200, 190], [190, 225, 120], [255, 220, 110], [255, 250, 235],
];

function ramp(t) {
  const u = Math.max(0, Math.min(1, t)) * (RAMP.length - 1);
  const i = Math.min(RAMP.length - 2, Math.floor(u)), f = u - i;
  const a = RAMP[i], b = RAMP[i + 1];
  return [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f,
          a[2] + (b[2] - a[2]) * f];
}

export async function mountTopo(root) {
  const grid = root.querySelector("[data-heads]");
  const tabs = root.querySelector("[data-topostate]");
  const note = root.querySelector("[data-toponote]");
  if (!grid) return;

  const all = await fetch("data/signals.json").then((r) => r.json());
  const sig = all.signals["eeg-topography"];
  if (!sig) return;

  let state = "closed";
  const R = 132;                       // pixels from centre to the head circle
  const SIZE = R * 2 + 34;

  function head(band) {
    const rows = sig.states[state];
    const cv = document.createElement("canvas");
    cv.width = cv.height = SIZE;
    cv.className = "headcv";
    const ctx = cv.getContext("2d");
    const img = ctx.createImageData(SIZE, SIZE);
    const cx = SIZE / 2, cy = SIZE / 2;

    /* Normalise each map over its own band across the two eye states, so the
       colour means the same thing when you flip between them and the eyes
       open map is not silently rescaled to look identical. */
    let lo = Infinity, hi = -Infinity;
    ["closed", "open"].forEach((st) => sig.states[st].forEach((r) => {
      lo = Math.min(lo, r.share[band]); hi = Math.max(hi, r.share[band]);
    }));

    const pts = rows.map((r) => ({
      x: cx + r.xy[0] * R, y: cy - r.xy[1] * R, v: r.share[band], ch: r.ch,
    }));

    for (let y = 0; y < SIZE; y++) {
      for (let x = 0; x < SIZE; x++) {
        const dx = x - cx, dy = y - cy;
        const rr = Math.hypot(dx, dy);
        const o = (y * SIZE + x) * 4;
        if (rr > R + 1) { img.data[o + 3] = 0; continue; }
        let num = 0, den = 0, exact = null;
        for (let k = 0; k < pts.length; k++) {
          const d2 = (x - pts[k].x) ** 2 + (y - pts[k].y) ** 2;
          if (d2 < 1) { exact = pts[k].v; break; }
          const w = 1 / (d2 * Math.sqrt(d2));   // inverse cube, a tight blend
          num += w * pts[k].v; den += w;
        }
        const v = exact != null ? exact : num / den;
        const c = ramp((v - lo) / (hi - lo || 1));
        img.data[o] = c[0]; img.data[o + 1] = c[1]; img.data[o + 2] = c[2];
        /* Feather the last two pixels so the disc does not look cut out. */
        img.data[o + 3] = rr > R - 1 ? 255 * (R + 1 - rr) / 2 : 255;
      }
    }
    ctx.putImageData(img, 0, 0);

    ctx.strokeStyle = "rgba(220,238,255,.45)";
    ctx.lineWidth = 1.5;
    ctx.beginPath(); ctx.arc(cx, cy, R, 0, Math.PI * 2); ctx.stroke();
    /* A nose, so which way the head faces is not something you have to be
       told. +y in the montage is anterior, and canvas y grows downward. */
    ctx.beginPath();
    ctx.moveTo(cx - 11, cy - R + 3);
    ctx.lineTo(cx, cy - R - 13);
    ctx.lineTo(cx + 11, cy - R + 3);
    ctx.stroke();

    pts.forEach((p) => {
      ctx.beginPath();
      ctx.arc(p.x, p.y, 2.1, 0, Math.PI * 2);
      ctx.fillStyle = "rgba(10,14,20,.75)";
      ctx.fill();
      ctx.strokeStyle = "rgba(230,244,255,.55)";
      ctx.lineWidth = 0.8;
      ctx.stroke();
    });

    const peak = pts.reduce((a, b) => (b.v > a.v ? b : a));
    return { cv, lo, hi, peak };
  }

  function draw() {
    grid.innerHTML = "";
    sig.bands.forEach((b) => {
      const { cv, lo, hi, peak } = head(b.name);
      const card = document.createElement("figure");
      card.className = "headcard";
      const cap = document.createElement("figcaption");
      cap.innerHTML = `<b>${b.name}</b><u>${b.low_Hz} to ${b.high_Hz} Hz</u>` +
        `<span>strongest at <b>${peak.ch}</b>, ${peak.v.toFixed(0)}%</span>`;
      card.appendChild(cv);
      card.appendChild(cap);
      grid.appendChild(card);
    });
    if (note) {
      note.innerHTML =
        `Eyes <b>${state}</b>. Each head is shaded by that band's share of the ` +
        `power at each of the 64 electrodes, on a scale shared between the two ` +
        `eye states so the comparison holds. Dots are where the electrodes ` +
        `actually are; everything between them is interpolated.`;
    }
  }

  if (tabs) {
    tabs.innerHTML = [["closed", "Eyes closed"], ["open", "Eyes open"]]
      .map(([k, l], i) => `<button type="button" role="tab" data-ts="${k}"` +
        ` aria-selected="${i === 0}">${l}</button>`).join("");
    tabs.addEventListener("click", (e) => {
      const b = e.target.closest("[data-ts]");
      if (!b) return;
      state = b.dataset.ts;
      tabs.querySelectorAll("[data-ts]").forEach((x) =>
        x.setAttribute("aria-selected", String(x === b)));
      draw();
    });
  }

  draw();
  return { draw, sig };
}
