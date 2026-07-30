/* The brain on two log axes: how big, and how long.
 *
 * Space runs from an ion channel to a whole head, time from ten microseconds
 * to a hundred years. Every process is a box at its real extent in both, and
 * every box says where its numbers came from. Three kinds of provenance, and
 * the page never blurs them: `measured` means a script in this repository
 * produced the number from data in this repository, `cited` means it is a
 * published range nobody here measured, `pending` means we mean to show real
 * data and do not have it yet.
 *
 * WHY SVG AND NOT WEBGL. This is a plot. It needs crisp small type, hit
 * testing that works with a keyboard, and about forty shapes. A canvas would
 * cost more and give less.
 *
 * THE POINT OF THE PICTURE. Nearly everything lies on a band where bigger
 * means slower. The exception is the nerve impulse, which crosses most of a
 * body in the time a synapse takes to answer, and that is what myelin buys.
 */
const NS = "http://www.w3.org/2000/svg";
const L10 = Math.log10;

function el(tag, attrs, parent) {
  const n = document.createElementNS(NS, tag);
  for (const k in attrs) n.setAttribute(k, attrs[k]);
  if (parent) parent.appendChild(n);
  return n;
}

/* Human readable durations and lengths, so an axis of powers of ten can still
 * be read by someone who does not think in powers of ten. */
function humanTime(s) {
  if (s < 1e-3) return `${Math.round(s * 1e6)} µs`;
  if (s < 1) return s < 0.01 ? `${(s * 1e3).toFixed(1)} ms` : `${Math.round(s * 1e3)} ms`;
  if (s < 90) return `${s < 10 ? s.toFixed(1) : Math.round(s)} s`;
  if (s < 5400) return `${Math.round(s / 60)} min`;
  if (s < 1.7e5) return `${Math.round(s / 3600)} hours`;
  if (s < 5e6) return `${Math.round(s / 86400)} days`;
  if (s < 6e7) return `${Math.round(s / 2.63e6)} months`;
  return `${Math.round(s / 3.15e7)} years`;
}
function humanSpace(m) {
  if (m < 1e-6) return `${Math.round(m * 1e9)} nm`;
  if (m < 1e-3) return `${m < 1e-5 ? (m * 1e6).toFixed(1) : Math.round(m * 1e6)} µm`;
  if (m < 1) return `${m < 1e-2 ? (m * 1e3).toFixed(m < 3e-3 ? 2 : 1) : Math.round(m * 1e3)} mm`;
  return `${m.toFixed(2)} m`;
}

export async function mountScales(root) {
  const plot = root.querySelector("[data-plot]");
  const panel = root.querySelector("[data-panel]");
  const legend = root.querySelector("[data-legend]");
  if (!plot) return;

  const db = await fetch("data/scales.json").then((r) => r.json());
  const signals = await fetch("data/signals.json").then((r) => r.json())
    .then((d) => d.signals).catch(() => ({}));

  const AX = db.axes;
  const X0 = L10(AX.time.low), X1 = L10(AX.time.high);
  const Y0 = L10(AX.space.low), Y1 = L10(AX.space.high);

  const M = { l: 66, r: 18, t: 18, b: 54 };
  let W = 900, H = 560;

  const svg = el("svg", { xmlns: NS, class: "plane" }, plot);
  const gGrid = el("g", {}, svg);
  const gBand = el("g", {}, svg);
  const gBoxes = el("g", {}, svg);
  const gAxis = el("g", {}, svg);

  const fx = (t) => M.l + ((L10(t) - X0) / (X1 - X0)) * (W - M.l - M.r);
  const fy = (s) => H - M.b - ((L10(s) - Y0) / (Y1 - Y0)) * (H - M.t - M.b);

  let selected = null;

  function draw() {
    const box = plot.getBoundingClientRect();
    W = Math.max(420, Math.round(box.width));
    H = Math.max(380, Math.round(Math.min(660, W * 0.62)));
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    svg.setAttribute("width", W);
    svg.setAttribute("height", H);
    [gGrid, gBand, gBoxes, gAxis].forEach((g) => { g.textContent = ""; });

    /* --- grid, one line per decade --------------------------------------- */
    for (let e = Math.ceil(X0); e <= Math.floor(X1); e++) {
      const x = fx(Math.pow(10, e));
      el("line", { x1: x, x2: x, y1: M.t, y2: H - M.b, class: "grid" }, gGrid);
    }
    for (let e = Math.ceil(Y0); e <= Math.floor(Y1); e++) {
      const y = fy(Math.pow(10, e));
      el("line", { x1: M.l, x2: W - M.r, y1: y, y2: y, class: "grid" }, gGrid);
    }

    /* --- the band where almost everything lies ---------------------------
       Drawn from the processes themselves rather than chosen: it is the least
       squares line through their centres, so the shape of the cloud is what
       positions it. */
    const pts = db.processes.map((p) => [
      (L10(p.time[0]) + L10(p.time[1])) / 2,
      (L10(p.space[0]) + L10(p.space[1])) / 2,
    ]);
    const n = pts.length;
    const mx = pts.reduce((s, p) => s + p[0], 0) / n;
    const my = pts.reduce((s, p) => s + p[1], 0) / n;
    const b = pts.reduce((s, p) => s + (p[0] - mx) * (p[1] - my), 0) /
              pts.reduce((s, p) => s + (p[0] - mx) ** 2, 0);
    const a = my - b * mx;
    const resid = pts.map((p) => p[1] - (a + b * p[0]));
    const sd = Math.sqrt(resid.reduce((s, r) => s + r * r, 0) / n);
    const line = (o) => `M ${fx(Math.pow(10, X0))} ${fy(Math.pow(10, a + b * X0 + o))} ` +
                        `L ${fx(Math.pow(10, X1))} ${fy(Math.pow(10, a + b * X1 + o))}`;
    el("path", {
      d: `${line(sd)} L ${fx(Math.pow(10, X1))} ${fy(Math.pow(10, a + b * X1 - sd))} ` +
         `L ${fx(Math.pow(10, X0))} ${fy(Math.pow(10, a + b * X0 - sd))} Z`,
      class: "band",
    }, gBand);
    el("path", { d: line(0), class: "bandline" }, gBand);

    /* --- what H01 covers -------------------------------------------------- */
    const cov = db.coverage;
    if (cov) {
      el("rect", {
        x: M.l, y: fy(cov.space[1]), width: W - M.l - M.r,
        height: Math.abs(fy(cov.space[0]) - fy(cov.space[1])),
        class: "coverage",
      }, gBand);
    }

    /* --- the processes ---------------------------------------------------- */
    db.processes.forEach((p) => {
      const x = fx(p.time[0]), y = fy(p.space[1]);
      const w = Math.max(7, fx(p.time[1]) - x);
      const h = Math.max(7, fy(p.space[0]) - y);
      const g = el("g", {
        class: "proc" + (selected === p.id ? " on" : ""),
        "data-id": p.id, tabindex: "0", role: "button",
        "aria-label": `${p.name}, ${humanSpace(p.space[0])} to ${humanSpace(p.space[1])}, ` +
                      `${humanTime(p.time[0])} to ${humanTime(p.time[1])}`,
      }, gBoxes);
      g.style.setProperty("--cc", db.domains[p.domain].color);
      el("rect", { x, y, width: w, height: h, rx: 3, class: "pbox" }, g);
      if (p.evidence === "measured") {
        el("circle", { cx: x + w - 5, cy: y + 5, r: 2.6, class: "meas" }, g);
      }
      const t = el("text", { x: x + w / 2, y: y - 6, class: "plab" }, g);
      t.textContent = p.name;
    });

    /* --- axes -------------------------------------------------------------- */
    el("line", { x1: M.l, x2: W - M.r, y1: H - M.b, y2: H - M.b, class: "axis" }, gAxis);
    el("line", { x1: M.l, x2: M.l, y1: M.t, y2: H - M.b, class: "axis" }, gAxis);
    AX.time.landmarks.forEach((l) => {
      const x = fx(l.at);
      el("line", { x1: x, x2: x, y1: H - M.b, y2: H - M.b + 5, class: "tick" }, gAxis);
      const a1 = el("text", { x, y: H - M.b + 18, class: "tlab" }, gAxis);
      a1.textContent = humanTime(l.at);
      const a2 = el("text", { x, y: H - M.b + 31, class: "tsub" }, gAxis);
      a2.textContent = l.label;
    });
    AX.space.landmarks.forEach((l) => {
      const y = fy(l.at);
      el("line", { x1: M.l - 5, x2: M.l, y1: y, y2: y, class: "tick" }, gAxis);
      const a1 = el("text", { x: M.l - 9, y: y - 1, class: "slab" }, gAxis);
      a1.textContent = humanSpace(l.at);
      const a2 = el("text", { x: M.l - 9, y: y + 10, class: "ssub" }, gAxis);
      a2.textContent = l.label;
    });
  }

  /* ---- the detail panel --------------------------------------------------- */
  function sparkline(sig, trace) {
    const xs = trace.x, ys = trace.y;
    const w = 320, h = 92, pad = 4;
    const xmin = Math.min(...xs), xmax = Math.max(...xs);
    const ymin = Math.min(...ys), ymax = Math.max(...ys);
    const px = (v) => pad + ((v - xmin) / (xmax - xmin || 1)) * (w - 2 * pad);
    const py = (v) => h - pad - ((v - ymin) / (ymax - ymin || 1)) * (h - 2 * pad);
    let d = "";
    for (let i = 0; i < xs.length; i++) {
      d += `${i ? "L" : "M"} ${px(xs[i]).toFixed(1)} ${py(ys[i]).toFixed(1)} `;
    }
    return `<svg class="spark" viewBox="0 0 ${w} ${h}" width="100%" ` +
      `preserveAspectRatio="none" aria-hidden="true"><path d="${d}"/></svg>` +
      `<div class="sparkax"><span>${xmin.toFixed(xmax - xmin < 1 ? 2 : 1)} to ` +
      `${xmax.toFixed(xmax - xmin < 1 ? 2 : 1)} ${sig.x_label}</span>` +
      `<span>${Math.round(ymin)} to ${Math.round(ymax)} ${sig.y_label}</span></div>`;
  }

  /* A scatter with a fitted line, for the one signal whose x axis is decades
     rather than milliseconds. Two series share the axes so the contrast
     between them is the thing you see. */
  function scatter(sig) {
    const ser = Object.values(sig.series);
    const w = 320, h = 116, pad = 6;
    const all = ser.flatMap((s) => s.x);
    const ally = ser.flatMap((s) => s.y);
    const xmin = Math.min(...all), xmax = Math.max(...all);
    const ymin = Math.min(...ally), ymax = Math.max(...ally);
    const px = (v) => pad + ((v - xmin) / (xmax - xmin)) * (w - 2 * pad);
    const py = (v) => h - pad - ((v - ymin) / (ymax - ymin)) * (h - 2 * pad);
    const COL = ["#7BE4FF", "#FFB24D"];
    let g = "";
    ser.forEach((s, i) => {
      s.x.forEach((xv, k) => {
        g += `<circle cx="${px(xv).toFixed(1)}" cy="${py(s.y[k]).toFixed(1)}" ` +
          `r="2.1" fill="${COL[i]}" opacity=".8"/>`;
      });
      /* Least squares through this series' own points, drawn so the eye is
         not left to guess a trend that the correlation already states. */
      const n = s.x.length;
      const mx = s.x.reduce((a, b) => a + b, 0) / n;
      const my = s.y.reduce((a, b) => a + b, 0) / n;
      const b1 = s.x.reduce((a, xv, k) => a + (xv - mx) * (s.y[k] - my), 0) /
                 s.x.reduce((a, xv) => a + (xv - mx) ** 2, 0);
      const a0 = my - b1 * mx;
      g += `<line x1="${px(xmin)}" y1="${py(a0 + b1 * xmin).toFixed(1)}" ` +
        `x2="${px(xmax)}" y2="${py(a0 + b1 * xmax).toFixed(1)}" ` +
        `stroke="${COL[i]}" stroke-width="1.4" opacity=".9"/>`;
    });
    return `<svg class="spark tall" viewBox="0 0 ${w} ${h}" width="100%" ` +
      `preserveAspectRatio="none" aria-hidden="true">${g}</svg>` +
      `<div class="sparkax"><span>${Math.round(xmin)} to ${Math.round(xmax)} ` +
      `${sig.x_label}</span><span>${sig.y_label}</span></div>` +
      ser.map((s, i) =>
        `<p class="tlabel"><span><s style="background:${COL[i]}"></s>${s.label}</span>` +
        `<b>r = ${s.r_with_age}</b></p>`).join("");
  }

  function show(id) {
    selected = id;
    draw();
    const p = db.processes.find((x) => x.id === id);
    if (!p) {
      panel.innerHTML = `<p class="hint">Pick anything on the map. Every box is
        placed at how big the thing is and how long it takes, both on scales of
        powers of ten, and says where its numbers came from.</p>`;
      return;
    }
    const dom = db.domains[p.domain];
    const ev = p.evidence;
    let html =
      `<h3 style="--cc:${dom.color}">${p.name}</h3>` +
      `<p class="tags"><span class="pill" style="--cc:${dom.color}">${dom.label}</span>` +
      `<span class="pill ev ev-${ev}">${ev === "measured" ? "measured here"
        : ev === "cited" ? "cited" : "not yet"}</span></p>` +
      `<div class="rows">` +
      `<div><dt>How big</dt><dd>${humanSpace(p.space[0])} to ${humanSpace(p.space[1])}</dd></div>` +
      `<div><dt>How long</dt><dd>${humanTime(p.time[0])} to ${humanTime(p.time[1])}</dd></div>` +
      `</div>` +
      `<p class="blurb">${p.blurb}</p>`;

    const sig = p.signal && signals[p.signal];
    if (sig) {
      html += `<div class="trace"><h4>${sig.title}</h4>`;
      if (sig.series) {
        html += scatter(sig);
        const ser = Object.values(sig.series);
        html += `<p class="tnote">Each dot is one person. ` +
          `${ser[0].label} falls by ${Math.abs(ser[0].slope_per_decade).toFixed(3)} ` +
          `per decade. ${ser[1].label} falls by ` +
          `${Math.abs(ser[1].slope_per_decade).toFixed(3)}, which on ` +
          `${ser[1].n} people is no reliable change at all.</p>`;
      } else if (sig.traces) {
        Object.values(sig.traces).forEach((t) => {
          html += `<p class="tlabel">Eyes ${t.state}, channel ${t.channel}` +
            `<b>${t.alpha_over_theta}&times;</b> alpha over theta</p>` +
            sparkline(sig, t);
        });
        html += `<p class="tnote">Closing the eyes multiplies the alpha rhythm ` +
          `by <b>${sig.blocking_ratio}</b>. Same person, same electrode, one ` +
          `minute apart.</p>`;
      } else {
        html += sparkline(sig, sig);
        if (sig.stats) {
          html += `<div class="rows">` + Object.entries(sig.stats).map(([k, v]) =>
            `<div><dt>${k.replace(/_/g, " ").replace(" mV", "").replace(" ms", "")
              .replace("V per s", "rate")}</dt><dd>${v}</dd></div>`).join("") + `</div>`;
        }
        if (sig.channel) html += `<p class="tnote">Channel ${sig.channel}.</p>`;
      }
      html += `<p class="prov">${sig.citation} Licence ${sig.licence}.</p></div>`;
    }
    html += `<p class="prov">${p.source}</p>`;
    panel.innerHTML = html;
  }

  plot.addEventListener("click", (e) => {
    const g = e.target.closest("[data-id]");
    show(g ? (g.dataset.id === selected ? null : g.dataset.id) : null);
  });
  plot.addEventListener("keydown", (e) => {
    if (e.key !== "Enter" && e.key !== " ") return;
    const g = e.target.closest("[data-id]");
    if (!g) return;
    e.preventDefault();
    show(g.dataset.id === selected ? null : g.dataset.id);
  });

  if (legend) {
    legend.innerHTML = Object.entries(db.domains).map(([, d]) =>
      `<span class="lk"><s style="background:${d.color}"></s>${d.label}</span>`).join("") +
      `<span class="lk"><s class="dot"></s>has a real recording behind it</span>`;
  }

  new ResizeObserver(() => draw()).observe(plot);
  draw();
  show(null);
  return { show, db, signals };
}
