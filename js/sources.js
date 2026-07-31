/* The rhythms, on the cortex, by solving the inverse problem.
 *
 * WHAT IS REAL HERE. The recording is 64 channels of one person, eyes closed
 * and eyes open. The head is fsaverage with its own three shell boundary
 * element model. The forward model says how a current dipole at each of 20,484
 * cortical points would look at each electrode; the dSPM inverse runs that
 * backwards. Every number is produced by scripts/fetch_sources.py, which
 * refuses to write the file unless alpha lands in visual cortex, delta does
 * not, and the eyes-closed alpha is at least three times the eyes-open alpha.
 * It measured 70 per cent, 40 per cent, and 19.4 times.
 *
 * WHAT IT IS NOT. An inverse solution is one of infinitely many current
 * distributions that produce the same scalp voltages. The problem is genuinely
 * ill posed, and the answer you get is the answer your prior asked for: dSPM
 * assumes current spread smoothly over the cortical sheet. This is a standard,
 * published kind of estimate. It is not a measurement of where the rhythm is.
 *
 * AND THE HEAD IS NOT THIS PERSON'S. fsaverage is an average of many brains,
 * and the electrodes are placed on it by the standard template rather than
 * measured on the head that was recorded.
 */
import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { DRACOLoader } from "three/addons/loaders/DRACOLoader.js";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { REDUCED, makeRenderer, fitRenderer, makeLoop, fmt } from "./holo3d.js";

/* Cold at rest, hot where the band is strong. Diverging would be wrong: this
 * is power, which has a floor and no meaningful midpoint. */
const RAMP = [
  [14, 18, 28], [30, 52, 96], [40, 120, 186],
  [58, 200, 186], [190, 226, 118], [255, 216, 96], [255, 252, 240],
];

function ramp(t) {
  const u = Math.max(0, Math.min(1, t)) * (RAMP.length - 1);
  const i = Math.min(RAMP.length - 2, Math.floor(u)), f = u - i;
  const a = RAMP[i], b = RAMP[i + 1];
  return [(a[0] + (b[0] - a[0]) * f) / 255,
          (a[1] + (b[1] - a[1]) * f) / 255,
          (a[2] + (b[2] - a[2]) * f) / 255];
}

/* FreeSurfer's region names are run together and lower case. These are the
 * same regions written the way an anatomist would say them. */
const REGION = {
  lateraloccipital: "lateral occipital cortex", lingual: "lingual gyrus",
  cuneus: "cuneus", pericalcarine: "calcarine cortex", precuneus: "precuneus",
  superiorparietal: "superior parietal cortex",
  superiortemporal: "superior temporal cortex",
  middletemporal: "middle temporal cortex",
  inferiortemporal: "inferior temporal cortex",
  precentral: "precentral gyrus", postcentral: "postcentral gyrus",
  supramarginal: "supramarginal gyrus", inferiorparietal: "inferior parietal cortex",
  superiorfrontal: "superior frontal cortex", rostralmiddlefrontal: "middle frontal cortex",
  fusiform: "fusiform gyrus", insula: "insula", paracentral: "paracentral lobule",
};

/* Signed, so it must diverge from zero. A sequential ramp on an oscillation
 * shows two peaks for every real cycle, because it cannot tell -1 from +1. */
const SWING = [[70, 130, 255], [30, 60, 130], [10, 12, 18],
               [130, 55, 30], [255, 150, 60]];
function swing(t) {
  const u = (Math.max(-1, Math.min(1, t)) + 1) / 2 * (SWING.length - 1);
  const i = Math.min(SWING.length - 2, Math.floor(u)), f = u - i;
  const a = SWING[i], b = SWING[i + 1];
  return [(a[0] + (b[0] - a[0]) * f) / 255, (a[1] + (b[1] - a[1]) * f) / 255,
          (a[2] + (b[2] - a[2]) * f) / 255];
}

const VIEWS = {
  left: [-1, -0.06, 0.12], right: [1, -0.06, 0.12],
  back: [0.04, -1, 0.12], top: [0.02, -0.12, 1],
};

export async function mountSources(el) {
  const mount = el.querySelector("[data-mount]");
  const bandEl = el.querySelector("[data-band]");
  const stateEl = el.querySelector("[data-srcstate]");
  const viewEl = el.querySelector("[data-srcview]");
  const infoEl = el.querySelector("[data-srcinfo]");
  const status = el.querySelector("[data-status]");
  if (!mount) return;

  const db = await fetch("data/sources.json").then((r) => r.json());
  const buf = await fetch(db.bin).then((r) => r.arrayBuffer());
  /* The inverse was solved on 10,242 points per hemisphere, which is the right
     density for an ill-posed problem and a coarse thing to look at. These are
     the full 163,842 vertex fsaverage surfaces, plus, for each vertex, which
     source is nearest to it on the sphere. Sixteen times the surface, exactly
     the same data underneath, and the page says so. */
  const hi = await fetch("data/hires.json").then((r) => r.json());
  const hibuf = await fetch(hi.bin).then((r) => r.arrayBuffer());
  /* One index array per (hemisphere, surface). The inflated and folded meshes
     are compressed separately and Draco gives them different vertex orders, so
     they cannot share one. */
  const hidx = {};
  hi.layout.forEach((L) => {
    hidx[`${L.hemi}|${L.kind}`] = {
      idx: new Uint16Array(hibuf, L.offset, L.count),
      srcOffset: L.source_offset, count: L.count };
  });
  let surfKind = "inflated";
  /* The rhythm as it actually moves, not its average strength. Loaded lazily
     because it is four megabytes and the still is useful on its own. */
  let movie = null, movieBuf = null, playing = false, frame = 0, acc = 0;
  const SLOW = 8;   // times slower than real, stated on the page
  const byKey = {};
  db.layout.forEach((L) => {
    byKey[`${L.band}|${L.state}`] = new Float32Array(buf, L.offset, L.count);
  });

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(38, 16 / 9, 1, 3000);
  /* The source space is in FreeSurfer surface RAS, where Z is up, exactly like
     MNI. three.js assumes Y, so this is the same correction the tract page
     needed and for the same reason. */
  camera.up.set(0, 0, 1);
  const renderer = makeRenderer(mount);
  scene.add(new THREE.AmbientLight(0xffffff, 1.15));
  const key = new THREE.DirectionalLight(0xffffff, 0.95);
  key.position.set(-300, -200, 260);
  scene.add(key);
  const rim = new THREE.DirectionalLight(0x9fd0ff, 0.55);
  rim.position.set(260, 200, -160);
  scene.add(rim);

  const loader = new GLTFLoader();
  const draco = new DRACOLoader();
  draco.setDecoderPath("vendor/three/addons/libs/draco/gltf/");
  loader.setDRACOLoader(draco);

  const hemis = {};
  const order = ["lh", "rh"];
  const cache = {};
  async function loadSurf(h, kind) {
    const k = `${h}-${kind}`;
    if (cache[k]) return cache[k];
    const m = hi.meshes[k];
    const g = await new Promise((res, rej) =>
      loader.load(m.file, res, undefined, rej));
    const geo = g.scene.getObjectByProperty("isMesh", true).geometry;
    geo.computeVertexNormals();
    const col = new Float32Array(geo.attributes.position.count * 3);
    geo.setAttribute("color", new THREE.BufferAttribute(col, 3));
    cache[k] = geo;
    return geo;
  }
  for (const h of order) {
    const geo = await loadSurf(h, surfKind);
    const obj = new THREE.Mesh(geo, new THREE.MeshLambertMaterial({
      vertexColors: true, side: THREE.DoubleSide,
    }));
    /* Inflating a hemisphere expands it past the midline, so the two
       interpenetrate and read as one unrecognisable blob. Push them apart by
       enough to clear, and say so rather than pretending this is anatomy. */
    obj.position.x = (h === "lh" ? -1 : 1) * (surfKind === "inflated" ? 26 : 0);
    scene.add(obj);
    const k = hidx[`${h}|${surfKind}`];
    hemis[h] = { obj, geo, n: k.count, idx: k.idx, srcOffset: k.srcOffset };
  }

  const centre = new THREE.Vector3();
  const box = new THREE.Box3();
  order.forEach((h) => box.expandByObject(hemis[h].obj));
  box.getCenter(centre);

  const controls = new OrbitControls(camera, renderer.domElement);
  controls.target.copy(centre);
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;
  controls.enablePan = false;
  controls.minDistance = 120;
  controls.maxDistance = 800;
  controls.autoRotate = false;
  renderer.domElement.style.cursor = "grab";
  renderer.domElement.addEventListener("pointerdown", () => {
    renderer.domElement.style.cursor = "grabbing";
  });
  renderer.domElement.addEventListener("pointerup", () => {
    renderer.domElement.style.cursor = "grab";
  });

  const loop = makeLoop(el, (dt) => {
    if (playing && movie) {
      acc += dt;
      const per = 1 / (movie.fps / SLOW);
      if (acc >= per) { acc = 0; frame++; paintFrame(); }
    }
    controls.update();
    renderer.render(scene, camera);
  });
  fitRenderer(renderer, camera, mount);
  new ResizeObserver(() => { if (fitRenderer(renderer, camera, mount)) loop.once(); })
    .observe(mount);

  function setView(k) {
    const v = new THREE.Vector3(...(VIEWS[k] || VIEWS.back)).normalize()
      .multiplyScalar(330);
    camera.position.copy(centre).add(v);
    controls.target.copy(centre);
    controls.update();
    loop.once();
  }

  let band = "alpha", state = "closed";

  function paintFrame() {
    const L = movie.layout.find((x) => x.state === state);
    const n = L.sources, fr = frame % L.frames;
    const raw = new Int8Array(movieBuf, L.offset + fr * n, n);
    /* Both states share one scale, so the collapse when the eyes open is
       something you can see rather than something normalised away. */
    const rel = L.relative_amplitude;
    order.forEach((h) => {
      const H = hemis[h];
      const col = H.geo.attributes.color.array;
      for (let i = 0; i < H.n; i++) {
        /* A square root on the magnitude, sign kept. Cortical current is
           very unevenly distributed, so on a linear scale everything but the
           few strongest sources sits at the dark centre of the diverging
           ramp and the rhythm is invisible. This expands the middle without
           ever moving a value across zero, which is the one thing that would
           be a lie about an oscillation. */
        const v = raw[H.srcOffset + H.idx[i]] / 127 * rel;
        const c = swing(Math.sign(v) * Math.sqrt(Math.abs(v)));
        col[i * 3] = c[0]; col[i * 3 + 1] = c[1]; col[i * 3 + 2] = c[2];
      }
      H.geo.attributes.color.needsUpdate = true;
    });
    if (infoEl) {
      infoEl.innerHTML =
        `<b>alpha</b>, 8 to 13 Hz, eyes <b>${state}</b>, playing at ` +
        `<b>1/${SLOW}</b> real speed. Frame ${fr + 1} of ${L.frames}, ` +
        `${(fr / movie.fps).toFixed(2)} s into a ${movie.seconds} second clip. ` +
        `Blue and orange are the two directions the current swings; the eyes ` +
        `open clip is drawn on the same scale, at ` +
        `<b>${Math.round(rel * 100)}%</b> of the eyes closed amplitude.`;
    }
  }

  function paint() {
    if (playing && movie) { paintFrame(); loop.once(); return; }
    const vals = byKey[`${band}|${state}`];
    /* Both eye states share one scale, per band, so switching between them is
       a comparison rather than two separately stretched pictures. The stored
       values are already normalised to the eyes-closed maximum of that band,
       so this only has to apply the ratio between the two states' maxima. */
    const rec = db.bands.find((b) => b.name === band);
    const scale = rec.states[state].max / Math.max(
      rec.states.closed.max, rec.states.open.max);
    order.forEach((h) => {
      const H = hemis[h];
      const col = H.geo.attributes.color.array;
      /* Every full-resolution vertex takes its nearest source's value. This
         is nearest neighbour and nothing else: no smoothing is invented and
         the patches are the size of the source space's own resolution. */
      for (let i = 0; i < H.n; i++) {
        const c = ramp(vals[H.srcOffset + H.idx[i]] * scale);
        col[i * 3] = c[0]; col[i * 3 + 1] = c[1]; col[i * 3 + 2] = c[2];
      }
      H.geo.attributes.color.needsUpdate = true;
    });
    if (infoEl) {
      const tops = db.top_regions_eyes_closed[band] || [];
      const other = state === "closed" ? "open" : "closed";
      const ratio = rec.states[state].max / rec.states[other].max;
      infoEl.innerHTML =
        `<b>${band}</b>, ${rec.low_Hz} to ${rec.high_Hz} Hz, eyes ` +
        `<b>${state}</b>. ` +
        (tops.length
          ? `With the eyes closed its strongest sources sit in ` +
            tops.slice(0, 3).map(([r, n]) =>
              `<b>${REGION[r] || r}</b> ` +
              `(${Math.round(100 * n / 400)}%)`).join(", ") + ". "
          : "") +
        `This state is <b>${ratio >= 1 ? ratio.toFixed(1) + "&times; stronger" :
          (1 / ratio).toFixed(1) + "&times; weaker"}</b> than eyes ${other}.`;
    }
    loop.once();
  }

  function tabs(node, items, current, onPick) {
    if (!node) return;
    node.innerHTML = items.map(([k, l]) =>
      `<button type="button" role="tab" data-k="${k}"` +
      ` aria-selected="${k === current()}">${l}</button>`).join("");
    node.addEventListener("click", (e) => {
      const b = e.target.closest("[data-k]");
      if (!b) return;
      onPick(b.dataset.k);
      node.querySelectorAll("[data-k]").forEach((x) =>
        x.setAttribute("aria-selected", String(x === b)));
    });
  }

  tabs(bandEl, db.bands.map((b) => [b.name, b.name]), () => band,
       (k) => { band = k; paint(); });
  tabs(stateEl, [["closed", "Eyes closed"], ["open", "Eyes open"]],
       () => state, (k) => { state = k; paint(); });
  tabs(viewEl, [["back", "Back"], ["left", "Left"], ["right", "Right"],
                ["top", "Top"]], () => "back", (k) => setView(k));
  const kindEl = el.querySelector("[data-surfkind]");
  tabs(kindEl, [["inflated", "Inflated"], ["white", "Folded"]],
       () => surfKind, async (k) => {
    surfKind = k;
    for (const h of order) {
      const geo = await loadSurf(h, k);
      const m = hidx[`${h}|${k}`];
      hemis[h].obj.geometry = geo;
      hemis[h].geo = geo;
      hemis[h].idx = m.idx;
      hemis[h].n = m.count;
      hemis[h].srcOffset = m.srcOffset;
      hemis[h].obj.position.x = (h === "lh" ? -1 : 1) * (k === "inflated" ? 26 : 0);
    }
    paint();
  });

  /* Play control. The movie is fetched on the first press, not on load. */
  const playEl = el.querySelector("[data-play]");
  if (playEl) {
    playEl.addEventListener("click", async () => {
      if (!movie) {
        playEl.textContent = "Loading the rhythm";
        playEl.disabled = true;
        movie = await fetch("data/source-movie.json").then((r) => r.json());
        movieBuf = await fetch(movie.bin).then((r) => r.arrayBuffer());
        playEl.disabled = false;
      }
      playing = !playing;
      playEl.textContent = playing ? "Pause" : "Play the rhythm";
      playEl.setAttribute("aria-pressed", String(playing));
      if (!playing) paint(); else { frame = 0; acc = 0; paintFrame(); }
      loop.once();
    });
  }
  /* Changing band or eye state while playing should not leave a stale frame. */
  const _paint = paint;

  setView("back");
  paint();
  if (status) status.textContent = "";
  loop.run();
  return { loop, db, paint, camera, controls, hemis, setBand: (b) => { band = b; paint(); } };
}
