/* Every cell body in the volume, in the place the microscope found it.
 *
 * WHAT IS REAL HERE. All 49,379 points are rows of
 * gs://h01-release/data/20210601/c3/tables/somas.csv, the cell body table of
 * the H01 release. Each row carries a position in 8x8x33 nm voxels, a class
 * assigned by the release, and a cortical layer. Nothing is jittered, sampled
 * or laid out. The lamination you see is not drawn on: it is where the cell
 * bodies are.
 *
 * The seven surfaces are the release's own layer meshes, from
 * gs://h01-release/data/20210601/layers, the same boundaries the table's layer
 * column was assigned from. So the slabs and the points cannot disagree.
 *
 * ORIENTATION. The volume's X axis runs pia to white matter, so the scene is
 * built with X on screen-vertical and the pia at the top. Y, the tangential
 * axis, is screen-horizontal. Z is the 173 um the sectioning gave us, which is
 * why the whole thing is a wafer rather than a cube.
 *
 * WHY A SHADER AND NOT A REBUILT GEOMETRY. Filtering 49,379 points by class or
 * layer happens on every click. Rebuilding a BufferGeometry each time churns
 * several megabytes; a per point `show` attribute lets the vertex shader throw
 * the hidden ones off screen and costs one buffer update of 49 kB.
 */
import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { DRACOLoader } from "three/addons/loaders/DRACOLoader.js";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import {
  REDUCED, makeRenderer, fitRenderer, makeLoop, fmt,
} from "./holo3d.js";

/* One colour per class in the release's vocabulary. Neurons are the cool end,
 * glia the warm and green end, and the vascular cells the one red. The point of
 * the split is the panel's own headline: most of what is here is not a neuron,
 * and that has to be legible at a glance rather than read off a legend. */
export const TYPE_COLOR = {
  PYRAMIDAL: "#3E96F0",
  SPINY_STELLATE: "#7BE4FF",
  SPINY_ATYPICAL: "#5B7CFF",
  UNCLASSIFIED_NEURON: "#A9C6E8",
  INTERNEURON: "#B884FF",
  C_SHAPED: "#E27BD8",
  OLIGO: "#FFB24D",
  ASTROCYTE: "#3FE3B0",
  MG_OPC: "#D4FF7E",
  BLOOD_VESSEL_CELL: "#FF5C7A",
  UNKNOWN: "#6B7280",
};

export const TYPE_LABEL = {
  PYRAMIDAL: "Pyramidal cell",
  SPINY_STELLATE: "Spiny stellate cell",
  SPINY_ATYPICAL: "Spiny cell, atypical tree",
  UNCLASSIFIED_NEURON: "Neuron, unclassified",
  INTERNEURON: "Interneuron",
  C_SHAPED: "C shaped cell",
  OLIGO: "Oligodendrocyte",
  ASTROCYTE: "Astrocyte",
  MG_OPC: "Microglia or OPC",
  BLOOD_VESSEL_CELL: "Blood vessel cell",
  UNKNOWN: "Unknown",
};

/* The layer surfaces, pia first. Tinted along one ramp so depth reads as depth
 * and the six of them do not compete with the eleven cell colours. */
const LAYERS = [
  { file: "layer1", name: "Layer 1", col: "#9fd8ff" },
  { file: "layer2", name: "Layer 2", col: "#7cc0f8" },
  { file: "layer3", name: "Layer 3", col: "#63a6ee" },
  { file: "layer4", name: "Layer 4", col: "#4f8ce0" },
  { file: "layer5", name: "Layer 5", col: "#4172cc" },
  { file: "layer6", name: "Layer 6", col: "#3659b0" },
  { file: "white-matter", name: "White matter", col: "#8b7fd0" },
];

const VERT = `
attribute vec3 acolor;
attribute float show;
uniform float scale;
varying vec3 vcolor;
varying float vshow;
void main() {
  vcolor = acolor;
  vshow = show;
  vec4 mv = modelViewMatrix * vec4(position, 1.0);
  gl_PointSize = scale / -mv.z;
  gl_Position = projectionMatrix * mv;
}`;

/* A round point, not a square. gl_PointCoord is the only way to get one
 * without a texture, and discarding outside the disc keeps the additive
 * blending from stacking square corners into a grid. */
const FRAG = `
varying vec3 vcolor;
varying float vshow;
uniform float dim;
void main() {
  if (vshow < 0.5) discard;
  vec2 d = gl_PointCoord - vec2(0.5);
  float r = dot(d, d);
  if (r > 0.25) discard;
  float edge = smoothstep(0.25, 0.06, r);
  gl_FragColor = vec4(vcolor, edge * dim);
}`;

function hexToRgb(h) {
  const c = new THREE.Color(h);
  return [c.r, c.g, c.b];
}

export async function mountColumn(el) {
  const mount = el.querySelector("[data-mount]");
  const status = el.querySelector("[data-status]");
  const legend = el.querySelector("[data-legend]");
  const modes = el.querySelector("[data-modes]");
  const readout = el.querySelector("[data-readout]");
  if (!mount) return;

  if (status) status.textContent = "Loading 49,379 cell bodies";

  const meta = await fetch("data/somas.json").then((r) => r.json());
  const buf = await fetch(meta.bin).then((r) => r.arrayBuffer());
  /* The binary's layout is declared in the header rather than hard coded here,
     so a change to the packing cannot silently reinterpret the wrong bytes. */
  const n = meta.count;
  const off = {};
  meta.layout.forEach((f) => { off[f.field] = f.offset; });
  const xyz = new Float32Array(buf, off.xyz, n * 3);
  const depth = new Float32Array(buf, off.depth, n);
  const type = new Uint8Array(buf, off.type, n);
  const layer = new Uint8Array(buf, off.layer, n);

  /* Centre the cloud on its own bounding box and put depth on screen-vertical.
     Everything downstream is in millimetres, which keeps the camera numbers
     small and readable. */
  const lo = meta.bounds_um[0], hi = meta.bounds_um[1];
  const mid = [0, 1, 2].map((i) => (lo[i] + hi[i]) / 2);
  const pos = new Float32Array(n * 3);
  for (let i = 0; i < n; i++) {
    pos[i * 3] = (xyz[i * 3 + 1] - mid[1]) / 1000;      // tangential -> screen x
    pos[i * 3 + 1] = (xyz[i * 3] - mid[0]) / 1000;      // depth      -> screen y
    pos[i * 3 + 2] = (xyz[i * 3 + 2] - mid[2]) / 1000;  // section    -> screen z
  }

  /* Neuron, glia and everything else, as the paper groups them. "Everything
     else" is not empty and must not be quietly folded into the glia: 692 cells
     are unclassified and 285 line the blood vessels, and a glial count that
     swallowed them would be 33,007 rather than the paper's 32,315. */
  const NEURON = new Set(meta.neuronal);
  const GLIA = new Set(meta.glial);
  const isNeuron = new Uint8Array(n);
  const isGlia = new Uint8Array(n);
  for (let i = 0; i < n; i++) {
    const t = meta.types[type[i]];
    isNeuron[i] = NEURON.has(t) ? 1 : 0;
    isGlia[i] = GLIA.has(t) ? 1 : 0;
  }

  const acolor = new Float32Array(n * 3);
  const show = new Float32Array(n).fill(1);

  const scene = new THREE.Scene();
  /* The block is 3.9 mm through the cortex, 2.4 mm across and 0.17 mm thick:
     a tall narrow wafer. Seen face on it wastes most of a wide canvas and its
     thinness is invisible, so the opening view is three quarters on, where the
     depth axis still runs top to bottom but the slab reads as a slab.

     Nothing is done to make it fill a wide canvas, because it does not: the
     block really is that shape, and the black either side of it is the page's
     own. The distance is set so the 3.9 mm of cortex fills about nine tenths
     of the height, which is the one dimension worth filling. */
  const camera = new THREE.PerspectiveCamera(38, 16 / 9, 0.01, 100);
  camera.position.set(3.4, 0.25, 5.6);
  const renderer = makeRenderer(mount);

  const geom = new THREE.BufferGeometry();
  geom.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  geom.setAttribute("acolor", new THREE.BufferAttribute(acolor, 3));
  geom.setAttribute("show", new THREE.BufferAttribute(show, 1));
  const mat = new THREE.ShaderMaterial({
    vertexShader: VERT, fragmentShader: FRAG,
    uniforms: { scale: { value: 12 }, dim: { value: 0.13 } },
    transparent: true, depthWrite: false,
    blending: THREE.AdditiveBlending,
  });
  const points = new THREE.Points(geom, mat);
  scene.add(points);

  /* ---- the layer surfaces ------------------------------------------------
     Loaded after the points, because the points are the panel and the slabs
     are the context. FrontSide with depthWrite off: a translucent shell that
     writes depth culls the cells inside it. */
  const slabs = new THREE.Group();
  slabs.visible = false;
  scene.add(slabs);
  const loader = new GLTFLoader();
  const draco = new DRACOLoader();
  draco.setDecoderPath("vendor/three/addons/libs/draco/gltf/");
  loader.setDRACOLoader(draco);
  Promise.all(LAYERS.map((L) => new Promise((res) => {
    loader.load(`meshes/layers/${L.file}.glb`, (g) => {
      const m = g.scene.getObjectByProperty("isMesh", true);
      if (!m) return res(null);
      const p = m.geometry.attributes.position;
      const out = new Float32Array(p.count * 3);
      for (let k = 0; k < p.count; k++) {
        out[k * 3] = (p.getY(k) - mid[1]) / 1000;
        out[k * 3 + 1] = (p.getX(k) - mid[0]) / 1000;
        out[k * 3 + 2] = (p.getZ(k) - mid[2]) / 1000;
      }
      const g2 = new THREE.BufferGeometry();
      g2.setAttribute("position", new THREE.BufferAttribute(out, 3));
      g2.setIndex(m.geometry.index);
      g2.computeVertexNormals();
      const mesh = new THREE.Mesh(g2, new THREE.MeshBasicMaterial({
        color: new THREE.Color(L.col), transparent: true, opacity: 0.055,
        side: THREE.FrontSide, depthWrite: false,
        blending: THREE.AdditiveBlending,
      }));
      mesh.renderOrder = 1;
      slabs.add(mesh);
      res(mesh);
    }, undefined, () => res(null));
  }))).then(() => { loop.once(); });

  /* ---- the vasculature --------------------------------------------------
     The paper puts about 230 millimetres of blood vessel in this one block.
     It is in the same voxel frame as the cell bodies, so it needs no
     registration at all: the cells and the plumbing that feeds them were
     already in one coordinate system, and the only work is the same axis
     remap the points get. Loaded only when asked for, because it is 1.9 MB
     the reader may never want. */
  let vessels = null, vesselsWanted = false;
  const vesselEl = el.querySelector("[data-vessels]");

  function placeVessels(geo) {
    const p = geo.attributes.position;
    const out = new Float32Array(p.count * 3);
    for (let k = 0; k < p.count; k++) {
      out[k * 3] = (p.getY(k) - mid[1]) / 1000;
      out[k * 3 + 1] = (p.getX(k) - mid[0]) / 1000;
      out[k * 3 + 2] = (p.getZ(k) - mid[2]) / 1000;
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(out, 3));
    g.setIndex(geo.index);
    g.computeVertexNormals();
    return g;
  }

  function toggleVessels(on) {
    vesselsWanted = on;
    if (vessels) { vessels.visible = on; loop.once(); return; }
    if (!on) return;
    if (vesselEl) vesselEl.textContent = "Loading the vessels";
    loader.load("meshes/vessels/vessels.glb", (g) => {
      const m = g.scene.getObjectByProperty("isMesh", true);
      if (!m) return;
      vessels = new THREE.Mesh(placeVessels(m.geometry),
        new THREE.MeshBasicMaterial({
          color: new THREE.Color("#FF5C7A"), transparent: true, opacity: 0.30,
          side: THREE.FrontSide, depthWrite: false,
          blending: THREE.AdditiveBlending,
        }));
      vessels.renderOrder = 2;
      vessels.visible = vesselsWanted;
      scene.add(vessels);
      if (vesselEl) vesselEl.textContent = "Blood vessels";
      loop.once();
    }, undefined, () => {
      if (vesselEl) vesselEl.textContent = "The vessels did not load";
    });
  }

  if (vesselEl) {
    vesselEl.addEventListener("click", () => {
      const on = vesselEl.getAttribute("aria-pressed") !== "true";
      vesselEl.setAttribute("aria-pressed", String(on));
      toggleVessels(on);
    });
  }

  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;
  controls.enablePan = false;
  controls.minDistance = 1.4;
  controls.maxDistance = 16;
  controls.autoRotate = !REDUCED;
  controls.autoRotateSpeed = 0.55;
  renderer.domElement.style.cursor = "grab";
  renderer.domElement.addEventListener("pointerdown", () => {
    controls.autoRotate = false;
    renderer.domElement.style.cursor = "grabbing";
  });
  renderer.domElement.addEventListener("pointerup", () => {
    renderer.domElement.style.cursor = "grab";
  });

  const loop = makeLoop(el, () => {
    controls.update();
    renderer.render(scene, camera);
  });
  function fit() {
    if (!fitRenderer(renderer, camera, mount)) return false;
    /* Above 1000 px the reading panel is laid out down the left of the stage,
       so the volume is pushed into the right of the frame to sit beside it.
       This shifts the camera's view window rather than moving the cloud,
       because moving the cloud would make it orbit around a point that is no
       longer inside it. Order matters: fitRenderer resets the projection, so
       the offset has to be applied after it. */
    const w = mount.clientWidth, h = mount.clientHeight;
    if (w >= 1000) camera.setViewOffset(w, h, -0.17 * w, 0, w, h);
    else camera.clearViewOffset();
    /* Point size is in pixels, so a taller canvas needs bigger points or the
       cloud thins out as the panel grows. The base of 12 puts a point at
       roughly two pixels at the opening distance. Five pixels, which is what
       a comfortable looking point size suggests, covers the slab eight times
       over: 49,379 points is far more than the wafer's area in pixels, and
       the whole block renders as a solid white parallelogram. */
    mat.uniforms.scale.value = 12 * Math.min(2, mount.clientHeight / 460);
    return true;
  }
  /* Size it now rather than waiting for the observer's first delivery. A
     ResizeObserver delivers on a rendering step, and a document that is not
     being rendered never has one, so a canvas that only ever sizes itself from
     the observer can sit at its 300 by 150 default indefinitely. */
  fit();
  new ResizeObserver(() => { if (fit()) loop.once(); }).observe(mount);

  /* ---- state -------------------------------------------------------------
     Two independent choices: what the colour means, and which cells are drawn.
     Both write the same two attributes, so they compose without a rebuild. */
  let colorMode = "type";
  let filter = "all";

  const CLASS_COLOR = {
    neuron: hexToRgb("#4aa6ff"),
    glia: hexToRgb("#FFB24D"),
    other: hexToRgb("#7c8493"),
  };
  const LAYER_COLOR = LAYERS.map((L) => hexToRgb(L.col))
    .concat([hexToRgb("#4b5563")]);

  /* The depth ramp, normalised over the reliable part of the volume rather
     than over the raw minimum and maximum, so a handful of cells sitting just
     outside the surface do not take the whole warm end to themselves. */
  const RAMP = ["#ffe9a8", "#7BE4FF", "#3E96F0", "#6C5BE0", "#B884FF"]
    .map(hexToRgb);
  const DMAX = meta.cortex_depth_um;
  function rampAt(d) {
    const t = Math.max(0, Math.min(1, d / DMAX)) * (RAMP.length - 1);
    const i = Math.min(RAMP.length - 2, Math.floor(t)), f = t - i;
    const a = RAMP[i], b = RAMP[i + 1];
    return [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f,
            a[2] + (b[2] - a[2]) * f];
  }

  function repaint() {
    let shown = 0, shownNeurons = 0;
    for (let i = 0; i < n; i++) {
      const t = meta.types[type[i]];
      let vis = true;
      if (filter === "neurons") vis = !!isNeuron[i];
      else if (filter === "glia") vis = !!isGlia[i];
      else if (filter === "other") vis = !isNeuron[i] && !isGlia[i];
      else if (filter !== "all") {
        /* A filter key is either a class name from the type vocabulary or a
           layer name from the layer vocabulary. They cannot collide, so one
           test against each is enough and the legend can stay dumb. */
        vis = t === filter || meta.layers[layer[i]] === filter;
      }
      show[i] = vis ? 1 : 0;
      if (vis) { shown++; if (isNeuron[i]) shownNeurons++; }

      let c;
      if (colorMode === "depth") {
        c = rampAt(depth[i]);
      } else if (colorMode === "layer") {
        c = LAYER_COLOR[layer[i] < LAYER_COLOR.length ? layer[i] : LAYER_COLOR.length - 1];
      } else if (colorMode === "class") {
        c = isNeuron[i] ? CLASS_COLOR.neuron
          : isGlia[i] ? CLASS_COLOR.glia : CLASS_COLOR.other;
      } else {
        c = hexToRgb(TYPE_COLOR[t] || "#6B7280");
      }
      acolor[i * 3] = c[0]; acolor[i * 3 + 1] = c[1]; acolor[i * 3 + 2] = c[2];
    }
    geom.attributes.show.needsUpdate = true;
    geom.attributes.acolor.needsUpdate = true;
    /* Additive blending is what makes the cloud read as a volume rather than
       as a sheet of stickers, but 49,379 points stacked over one another sum
       straight to white and the middle of the block goes blank. The alpha has
       to fall as the count rises. These steps were set by reading the
       framebuffer back and printing it as a coarse luminance map, which is
       the only way to look at this canvas from here. */
    mat.uniforms.dim.value = shown > 30000 ? 0.17
      : shown > 12000 ? 0.26 : shown > 4000 ? 0.44 : 0.72;
    if (readout) {
      readout.innerHTML =
        `<b>${fmt(shown)}</b> cell bodies drawn` +
        (shown === n ? "" : ` of ${fmt(n)}`) +
        ` &middot; <b>${fmt(shownNeurons)}</b> ${shownNeurons === 1 ? "is a neuron" : "are neurons"}`;
    }
    loop.once();
  }

  /* ---- controls ---------------------------------------------------------- */
  if (modes) {
    modes.innerHTML = [
      ["type", "Cell class"],
      ["class", "Neuron or not"],
      ["layer", "Cortical layer"],
      ["depth", "Depth below the surface"],
    ].map(([k, label], i) =>
      `<button type="button" role="tab" data-mode="${k}"` +
      ` aria-selected="${i === 0}">${label}</button>`).join("");
    modes.addEventListener("click", (e) => {
      const b = e.target.closest("[data-mode]");
      if (!b) return;
      colorMode = b.dataset.mode;
      modes.querySelectorAll("[data-mode]").forEach((x) =>
        x.setAttribute("aria-selected", String(x === b)));
      buildLegend();
      repaint();
    });
  }

  function buildLegend() {
    if (!legend) return;
    let rows;
    if (colorMode === "depth") {
      /* A continuous scale needs a bar, not swatches. The layer bands are
         printed on it at their measured depths, which is the whole point:
         nobody drew those boundaries, they are where the cell bodies are. */
      const stops = RAMP.map((c, i) =>
        `rgb(${c.map((v) => Math.round(v * 255)).join(",")}) ` +
        `${(100 * i / (RAMP.length - 1)).toFixed(0)}%`).join(",");
      legend.innerHTML =
        `<div class="ramp"><div class="ramp-bar" style="background:` +
        `linear-gradient(90deg,${stops})"></div>` +
        `<div class="ramp-ticks">` +
        meta.layer_bands.filter((b) => b.reliable !== false).map((b) =>
          `<i style="left:${100 * b.median_um / DMAX}%">` +
          `<u>${b.layer.replace("Layer ", "L").replace("White matter", "WM")}</u>` +
          `</i>`).join("") + `</div>` +
        `<div class="ramp-lab"><span>the surface</span>` +
        `<span>${fmt(DMAX)} &micro;m deep</span></div></div>`;
      return;
    }
    if (colorMode === "layer") {
      rows = LAYERS.map((L, i) => ({
        key: L.name, col: L.col, label: L.name,
        n: meta.counts.layer[L.name] || 0,
      }));
    } else if (colorMode === "class") {
      rows = [
        { key: "neurons", col: "#4aa6ff", label: "Neurons", n: meta.neuron_count },
        { key: "glia", col: "#FFB24D", label: "Glia", n: meta.glia_count },
        { key: "other", col: "#7c8493", label: "Neither, or unclassified",
          n: meta.count - meta.neuron_count - meta.glia_count },
      ];
    } else {
      rows = meta.types.slice()
        .sort((a, b) => meta.counts.type[b] - meta.counts.type[a])
        .map((t) => ({
          key: t, col: TYPE_COLOR[t] || "#6B7280",
          label: TYPE_LABEL[t] || t, n: meta.counts.type[t],
        }));
    }
    legend.innerHTML = rows.map((r) =>
      `<button type="button" class="lg" data-filter="${r.key}"` +
      ` aria-pressed="${filter === r.key}"` +
      `><s style="background:${r.col}"></s><span>${r.label}</span>` +
      `<em>${fmt(r.n)}</em></button>`).join("") +
      `<button type="button" class="lg lg-all" data-filter="all"` +
      ` aria-pressed="${filter === "all"}">Show every cell</button>`;
  }

  if (legend) {
    legend.addEventListener("click", (e) => {
      const b = e.target.closest("[data-filter]");
      if (!b) return;
      const k = b.dataset.filter;
      filter = (filter === k && k !== "all") ? "all" : k;
      buildLegend();
      repaint();
    });
  }

  buildLegend();
  repaint();
  if (status) status.textContent = "";
  loop.run();
  return { loop, repaint };
}
