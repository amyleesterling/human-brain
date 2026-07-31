/* The map of visual space that is laid out on the back of your head.
 *
 * WHAT IS REAL HERE. One person's own inflated cortical surface, and at each
 * vertex the patch of visual space that vertex responds to, fitted from an
 * hour in a scanner while a bar and a wedge swept across their view.
 * OpenNeuro ds007283, NYU-NEI, CC0. scripts/fetch_retinotopy.py refuses to
 * write anything unless the maps are smooth across the cortical sheet far
 * beyond chance, with a shuffled control that has to score about 1. Measured:
 * neighbouring vertices differ 30 times less than random pairs.
 *
 * WHY POLAR ANGLE USES A COLOUR WHEEL. Angle is cyclic: -pi and +pi are the
 * same direction. A linear ramp on a cyclic quantity invents a seam that is
 * not in the data, and on a retinotopic map that fake seam sits right where
 * the real boundaries are, which is the worst possible place to lie.
 *
 * WHY MOST OF THE BRAIN IS GREY. Only about 27,000 vertices per hemisphere
 * have a receptive field the model can fit. Everywhere else the fit explains
 * almost nothing, and colouring it would be colouring noise. The threshold is
 * yours to move.
 */
import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { DRACOLoader } from "three/addons/loaders/DRACOLoader.js";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { REDUCED, makeRenderer, fitRenderer, makeLoop, fmt } from "./holo3d.js";

const GREY = [0.145, 0.157, 0.180];

/* Cyclic, for polar angle. Hue around the wheel is the one honest encoding of
 * a direction, and it is what every retinotopy paper uses. */
function angleColor(a) {
  const c = new THREE.Color();
  c.setHSL(((a + Math.PI) / (2 * Math.PI)) % 1, 0.72, 0.55);
  return [c.r, c.g, c.b];
}

/* Sequential, for eccentricity: it has a floor at the centre of gaze and no
 * meaningful midpoint, so it must not be cyclic and must not diverge. */
const ECC = [[26, 20, 64], [40, 84, 158], [40, 160, 168],
             [120, 208, 120], [242, 214, 96], [255, 246, 224]];
function eccColor(t) {
  const u = Math.max(0, Math.min(1, t)) * (ECC.length - 1);
  const i = Math.min(ECC.length - 2, Math.floor(u)), f = u - i;
  const a = ECC[i], b = ECC[i + 1];
  return [(a[0] + (b[0] - a[0]) * f) / 255, (a[1] + (b[1] - a[1]) * f) / 255,
          (a[2] + (b[2] - a[2]) * f) / 255];
}

const VIEWS = {
  back: [0.05, -1, 0.10], left: [-1, -0.25, 0.10], right: [1, -0.25, 0.10],
  below: [0.05, -0.45, -1],
};

export async function mountRetino(el) {
  const mount = el.querySelector("[data-mount]");
  const modeEl = el.querySelector("[data-rmode]");
  const viewEl = el.querySelector("[data-rview]");
  const hemiEl = el.querySelector("[data-rhemi]");
  const infoEl = el.querySelector("[data-rinfo]");
  const fieldEl = el.querySelector("[data-field]");
  const status = el.querySelector("[data-status]");
  if (!mount) return;

  const db = await fetch("data/retinotopy.json").then((r) => r.json());
  const buf = await fetch(db.bin).then((r) => r.arrayBuffer());
  const F = {};
  db.layout.forEach((L) => {
    F[`${L.hemi}|${L.field}`] = L.dtype === "uint16"
      ? new Uint16Array(buf, L.offset, L.count)
      : new Uint8Array(buf, L.offset, L.count);
  });

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(38, 16 / 9, 1, 3000);
  /* FreeSurfer surface RAS: Z is up, same as MNI, and three.js assumes Y. */
  camera.up.set(0, 0, 1);
  const renderer = makeRenderer(mount);
  scene.add(new THREE.AmbientLight(0xffffff, 1.2));
  const key = new THREE.DirectionalLight(0xffffff, 0.85);
  key.position.set(-200, -300, 220);
  scene.add(key);
  const rim = new THREE.DirectionalLight(0x9fd0ff, 0.5);
  rim.position.set(220, 240, -180);
  scene.add(rim);

  const loader = new GLTFLoader();
  const draco = new DRACOLoader();
  draco.setDecoderPath("vendor/three/addons/libs/draco/gltf/");
  loader.setDRACOLoader(draco);

  const hemis = {};
  for (const h of ["lh", "rh"]) {
    const m = db.meshes[h];
    // eslint-disable-next-line no-await-in-loop
    const g = await new Promise((res, rej) =>
      loader.load(m.file, res, undefined, rej));
    const geo = g.scene.getObjectByProperty("isMesh", true).geometry;
    geo.computeVertexNormals();
    const col = new Float32Array(geo.attributes.position.count * 3);
    geo.setAttribute("color", new THREE.BufferAttribute(col, 3));
    const obj = new THREE.Mesh(geo, new THREE.MeshLambertMaterial({
      vertexColors: true, side: THREE.DoubleSide,
    }));
    scene.add(obj);
    hemis[h] = { obj, geo, col, n: m.vertices };
  }

  const centre = new THREE.Vector3();
  new THREE.Box3().setFromObject(scene).getCenter(centre);

  const controls = new OrbitControls(camera, renderer.domElement);
  controls.target.copy(centre);
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;
  controls.enablePan = false;
  controls.minDistance = 130;
  controls.maxDistance = 900;
  renderer.domElement.style.cursor = "crosshair";

  const loop = makeLoop(el, () => { controls.update(); renderer.render(scene, camera); });
  fitRenderer(renderer, camera, mount);
  new ResizeObserver(() => { if (fitRenderer(renderer, camera, mount)) loop.once(); })
    .observe(mount);

  let mode = "angle", shown = "both", thresh = db.vexpl_threshold;
  let picked = null;                    // {angle, eccen, vexpl}

  function setView(k) {
    const v = new THREE.Vector3(...(VIEWS[k] || VIEWS.back)).normalize()
      .multiplyScalar(340);
    camera.position.copy(centre).add(v);
    controls.target.copy(centre);
    controls.update();
    loop.once();
  }

  function decode(h, i) {
    const a = F[`${h}|angle`][i] / 65535 * 2 * Math.PI - Math.PI;
    const e = F[`${h}|eccen`][i] / 65535 * db.eccen_range_deg[1];
    const x = F[`${h}|vexpl`][i] / 255;
    return { angle: a, eccen: e, vexpl: x };
  }

  function paint() {
    let n = 0;
    ["lh", "rh"].forEach((h) => {
      const H = hemis[h];
      H.obj.visible = shown === "both" || shown === h;
      for (let i = 0; i < H.n; i++) {
        const d = decode(h, i);
        let c;
        if (d.vexpl < thresh) {
          c = GREY;
        } else {
          n++;
          c = mode === "angle" ? angleColor(d.angle)
            : eccColor(d.eccen / db.eccen_range_deg[1] * 2.4);
        }
        H.col[i * 3] = c[0]; H.col[i * 3 + 1] = c[1]; H.col[i * 3 + 2] = c[2];
      }
      H.geo.attributes.color.needsUpdate = true;
    });
    if (infoEl) {
      const total = hemis.lh.n + hemis.rh.n;
      infoEl.innerHTML =
        `<b>${fmt(n)}</b> of ${fmt(total)} vertices have a receptive field the ` +
        `model can fit above ${Math.round(thresh * 100)}% variance explained. ` +
        `The rest is grey because colouring it would be colouring noise.` +
        (picked
          ? ` <span class="pick">This point sees <b>${picked.eccen.toFixed(1)}&deg;</b> ` +
            `from the centre of gaze, at <b>${(picked.angle * 180 / Math.PI).toFixed(0)}&deg;</b> ` +
            `around, fit ${Math.round(picked.vexpl * 100)}%.</span>`
          : ` <span class="pick">Click the coloured cortex to see where it looks.</span>`);
    }
    drawField();
    loop.once();
  }

  /* The visual field, drawn in the same colours as the cortex. This is the
     whole point of the page: the wheel and the brain are one map. */
  function drawField() {
    if (!fieldEl) return;
    const S = 260, R = S / 2 - 14, cx = S / 2, cy = S / 2;
    const cv = fieldEl.querySelector("canvas") || (() => {
      const c = document.createElement("canvas");
      fieldEl.appendChild(c);
      return c;
    })();
    cv.width = cv.height = S;
    const ctx = cv.getContext("2d");
    const img = ctx.createImageData(S, S);
    const maxE = db.eccen_range_deg[1] / 2.4;   // matches the cortex scaling
    for (let y = 0; y < S; y++) {
      for (let x = 0; x < S; x++) {
        const dx = x - cx, dy = cy - y;
        const r = Math.hypot(dx, dy), o = (y * S + x) * 4;
        if (r > R) { img.data[o + 3] = 0; continue; }
        const c = mode === "angle"
          ? angleColor(Math.atan2(dy, dx))
          : eccColor(r / R);
        img.data[o] = c[0] * 255; img.data[o + 1] = c[1] * 255;
        img.data[o + 2] = c[2] * 255;
        img.data[o + 3] = r > R - 1 ? 200 : 255;
      }
    }
    ctx.putImageData(img, 0, 0);
    ctx.strokeStyle = "rgba(220,238,255,.30)";
    ctx.lineWidth = 1;
    [0.25, 0.5, 0.75].forEach((f) => {
      ctx.beginPath(); ctx.arc(cx, cy, R * f, 0, Math.PI * 2); ctx.stroke();
    });
    ctx.beginPath(); ctx.moveTo(cx - R, cy); ctx.lineTo(cx + R, cy);
    ctx.moveTo(cx, cy - R); ctx.lineTo(cx, cy + R); ctx.stroke();
    /* Where you are looking. */
    ctx.fillStyle = "rgba(255,255,255,.85)";
    ctx.beginPath(); ctx.arc(cx, cy, 2.5, 0, Math.PI * 2); ctx.fill();
    if (picked && picked.vexpl >= thresh) {
      const rr = Math.min(1, picked.eccen / maxE) * R;
      const px = cx + rr * Math.cos(picked.angle);
      const py = cy - rr * Math.sin(picked.angle);
      ctx.strokeStyle = "#fff"; ctx.lineWidth = 2.5;
      ctx.beginPath(); ctx.arc(px, py, 7, 0, Math.PI * 2); ctx.stroke();
      ctx.strokeStyle = "rgba(0,0,0,.6)"; ctx.lineWidth = 1;
      ctx.beginPath(); ctx.arc(px, py, 9, 0, Math.PI * 2); ctx.stroke();
    }
  }

  /* Click the cortex, and the visual field shows you what that patch sees. */
  const ray = new THREE.Raycaster();
  const ndc = new THREE.Vector2();
  renderer.domElement.addEventListener("pointerdown", (ev) => {
    const r = renderer.domElement.getBoundingClientRect();
    ndc.x = ((ev.clientX - r.left) / r.width) * 2 - 1;
    ndc.y = -((ev.clientY - r.top) / r.height) * 2 + 1;
    ray.setFromCamera(ndc, camera);
    const objs = ["lh", "rh"].filter((h) => hemis[h].obj.visible)
      .map((h) => hemis[h].obj);
    const hit = ray.intersectObjects(objs, false)[0];
    if (!hit) return;
    const h = hit.object === hemis.lh.obj ? "lh" : "rh";
    /* The nearest of the face's three corners is the vertex the reader
       actually pointed at; interpolating a cyclic angle across a face would
       be wrong anyway. */
    const p = hemis[h].geo.attributes.position;
    const f = [hit.face.a, hit.face.b, hit.face.c];
    let best = f[0], bd = Infinity;
    f.forEach((i) => {
      const d = hit.point.distanceToSquared(
        new THREE.Vector3(p.getX(i), p.getY(i), p.getZ(i)));
      if (d < bd) { bd = d; best = i; }
    });
    picked = decode(h, best);
    paint();
  });

  function tabs(node, items, cur, pick) {
    if (!node) return;
    node.innerHTML = items.map(([k, l]) =>
      `<button type="button" role="tab" data-k="${k}"` +
      ` aria-selected="${k === cur}">${l}</button>`).join("");
    node.addEventListener("click", (e) => {
      const b = e.target.closest("[data-k]");
      if (!b) return;
      pick(b.dataset.k);
      node.querySelectorAll("[data-k]").forEach((x) =>
        x.setAttribute("aria-selected", String(x === b)));
    });
  }

  tabs(modeEl, [["angle", "Which way"], ["eccen", "How far out"]], "angle",
       (k) => { mode = k; paint(); });
  tabs(hemiEl, [["both", "Both"], ["lh", "Left"], ["rh", "Right"]], "both",
       (k) => { shown = k; paint(); });
  tabs(viewEl, [["back", "Back"], ["below", "Underneath"],
                ["left", "Left"], ["right", "Right"]], "back",
       (k) => setView(k));

  setView("back");
  paint();
  if (status) status.textContent = "";
  loop.run();
  return { loop, db, paint, camera, controls, hemis,
           setMode: (m) => { mode = m; paint(); },
           pick: (h, i) => { picked = decode(h, i); paint(); return picked; } };
}
