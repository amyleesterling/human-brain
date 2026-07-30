/* One cell of every kind in the volume, and what each kind is for.
 *
 * WHAT IS REAL HERE. Every mesh is a real reconstruction from the H01 electron
 * microscopy, and which cell stands for each class was decided by
 * scripts/pick_type_examples.py rather than by picking whichever loaded first:
 * eleven candidates per class, all measured, and the one closest to that
 * class's median longest axis wins. Every number beside a cell is counted from
 * the release's own soma table.
 *
 * WHAT IS NOT PROOFREAD. All eleven come from the c3 automatic agglomeration,
 * not from the 104 cells checked by hand, so any of them may carry a merge or
 * a split. The page says so on every card rather than in a footnote. The
 * sampled range printed on each card is the evidence: a blood vessel cell
 * sampled at 835 micrometres is a merge, not a cell.
 *
 * LEVEL OF DETAIL IS PER CELL. A whole astrocyte is 1.4 million faces at the
 * level where an oligodendrocyte is ten thousand, because surface area is what
 * an astrocyte is for. One level for all eleven either ships 55 MB or erases
 * the small cells.
 */
import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { DRACOLoader } from "three/addons/loaders/DRACOLoader.js";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import {
  REDUCED, makeRenderer, fitRenderer, makeLoop, studioLights, disposeTree, fmt,
} from "./holo3d.js";
import { TYPE_COLOR } from "./column.js";

/* What each kind of cell is for. The first sentence is what it does, which is
 * general neuroscience and not something this volume measured. Anything with a
 * number in it is from H01 and is printed separately on the card. */
const NOTES = {
  PYRAMIDAL: {
    tag: "The cortex's output cell",
    text: "Excitatory. One thick apical dendrite climbing toward the surface, " +
      "basal dendrites spread around the cell body, and an axon that can leave " +
      "the cortex entirely to reach another region. Covered in spines, each of " +
      "which is a place a synapse can land.",
  },
  INTERNEURON: {
    tag: "The local brake",
    text: "Inhibitory, and almost entirely local: its axon stays near its own " +
      "cell body rather than leaving. Not spiny. The release classified as an " +
      "interneuron any neuron that was neither spiny nor pyramidal in shape, " +
      "so this is a category defined by what a cell is not.",
  },
  SPINY_STELLATE: {
    tag: "Excitatory, and going nowhere",
    text: "Spiny and excitatory like a pyramidal cell, but with no apical " +
      "dendrite: the branches radiate in every direction instead of climbing. " +
      "Classically the layer 4 cell that receives what arrives from the " +
      "thalamus. The rarest neuron in this block.",
  },
  SPINY_ATYPICAL: {
    tag: "Excitatory, oddly shaped",
    text: "Spiny, and therefore excitatory, but with a dendritic tree that " +
      "does not fit the pyramidal pattern. The release keeps these separate " +
      "rather than forcing them into a category they do not belong in.",
  },
  UNCLASSIFIED_NEURON: {
    tag: "A neuron that would not sort",
    text: "Clearly a neuron, but not clearly which kind. The paper says most " +
      "of these are cells whose bodies were not fully inside the block, so " +
      "there was simply not enough of them to judge.",
  },
  OLIGO: {
    tag: "The insulator",
    text: "Not a neuron. It wraps axons in myelin, which is what lets a nerve " +
      "impulse cross a metre in milliseconds instead of a second. Densest deep " +
      "in the white matter, because that is where the axons are. There are " +
      "more of these in this block than every neuron put together.",
  },
  ASTROCYTE: {
    tag: "Mostly surface",
    text: "Not a neuron. Its finest processes wrap synapses and reach the " +
      "blood vessels, and neighbouring astrocytes tile the tissue with little " +
      "overlap. Surface area is the whole job, which is why this one cell " +
      "carries more geometry than any other on this page.",
  },
  MG_OPC: {
    tag: "Immune cell, or a precursor",
    text: "Two kinds of glia that look so alike the release could not " +
      "separate them by shape. A machine learning method predicted 2,517 " +
      "microglia, the brain's resident immune cell and the only one that " +
      "travels through the tissue, and 1,626 oligodendrocyte precursors, with " +
      "2,102 left unclassified. The soma table keeps all three as one class.",
  },
  C_SHAPED: {
    tag: "Named for its shape, counted with the glia",
    text: "The class that settles the arithmetic. Counted as a neuron, none " +
      "of the paper's totals match. Counted with the glia, all three come out " +
      "exactly right, which is how this page knows where it belongs.",
  },
  BLOOD_VESSEL_CELL: {
    tag: "The plumbing",
    text: "Endothelial cells lining the inside of a vessel, and pericytes " +
      "wrapped around the outside. The release counts 4,604 endothelial cells " +
      "and 3,549 pericytes and other perivascular types along roughly 230 " +
      "millimetres of vessel, but only a few hundred of them appear in this " +
      "soma table: the vasculature has a layer of its own.",
  },
  UNKNOWN: {
    tag: "Not classified",
    text: "A cell body the release could see but did not name.",
  },
};

const GROUP_LABEL = { neuron: "Neuron", glia: "Glia", other: "Neither" };

/* ------------------------------------------------------------ the chart ---
   A table of eleven percentages is a table. The thing worth seeing is that
   two thirds of this tissue is not neurons, so the chart is two bars against
   one width: the three groups above, the eleven classes below, so you can see
   which classes make up which group. */
export function mountRatios(root, meta) {
  const bar = root.querySelector("[data-ratio]");
  if (!bar) return;
  const n = meta.count;
  const NEU = new Set(meta.neuronal), GLI = new Set(meta.glial);
  const groupOf = (t) => NEU.has(t) ? "neuron" : GLI.has(t) ? "glia" : "other";

  const groups = [
    { key: "glia", n: meta.glia_count, col: "#FFB24D" },
    { key: "neuron", n: meta.neuron_count, col: "#4aa6ff" },
    { key: "other", n: n - meta.glia_count - meta.neuron_count, col: "#7c8493" },
  ];
  /* Classes ordered by group first so the two bars line up and the eye can
     read straight down from a group into the classes that make it. */
  const classes = meta.types.slice().sort((a, b) => {
    const ga = groups.findIndex((g) => g.key === groupOf(a));
    const gb = groups.findIndex((g) => g.key === groupOf(b));
    return ga - gb || meta.counts.type[b] - meta.counts.type[a];
  });

  const seg = (label, count, col, title) => {
    const pct = 100 * count / n;
    return `<i style="width:${pct}%;background:${col}" title="${title}">` +
      (pct > 7 ? `<b>${label}</b><u>${pct.toFixed(1)}%</u>` : "") + `</i>`;
  };

  bar.innerHTML =
    `<div class="rbar rbar-top">` +
    groups.map((g) => seg(GROUP_LABEL[g.key], g.n, g.col,
      `${GROUP_LABEL[g.key]}: ${fmt(g.n)}`)).join("") + `</div>` +
    `<div class="rbar rbar-cls">` +
    classes.map((t) => seg("", meta.counts.type[t], TYPE_COLOR[t] || "#6B7280",
      `${t}: ${fmt(meta.counts.type[t])}`)).join("") + `</div>` +
    `<div class="rkey">` +
    classes.map((t) =>
      `<span class="rk"><s style="background:${TYPE_COLOR[t] || "#6B7280"}"></s>` +
      `${t.replace(/_/g, " ").toLowerCase()}<em>${(100 * meta.counts.type[t] / n).toFixed(1)}%</em></span>`
    ).join("") + `</div>`;
}

/* ---------------------------------------------------------- the gallery --- */
export async function mountTypes(el) {
  const mount = el.querySelector("[data-mount]");
  const rail = el.querySelector("[data-rail]");
  const info = el.querySelector("[data-info]");
  const status = el.querySelector("[data-status]");
  if (!mount || !rail) return;

  const man = await fetch("meshes/types/manifest.json").then((r) => r.json());
  const soma = await fetch("data/somas.json").then((r) => r.json());
  const NEU = new Set(soma.neuronal), GLI = new Set(soma.glial);
  const groupOf = (t) => NEU.has(t) ? "neuron" : GLI.has(t) ? "glia" : "other";

  /* Neurons first, then glia, then the rest, each block by how common it is.
     A gallery ordered by raw count opens on an oligodendrocyte, which is true
     but is a poor first impression of what a brain cell looks like. */
  const order = { neuron: 0, glia: 1, other: 2 };
  const types = man.types.slice().sort((a, b) =>
    order[groupOf(a.class)] - order[groupOf(b.class)] || b.count - a.count);

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(42, 16 / 9, 0.01, 200);
  camera.position.set(0, 0, 2.6);
  const renderer = makeRenderer(mount);
  studioLights(scene, "#3E96F0");

  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;
  controls.enablePan = false;
  controls.minDistance = 0.8;
  controls.maxDistance = 12;
  controls.autoRotate = !REDUCED;
  controls.autoRotateSpeed = 1.0;
  renderer.domElement.style.cursor = "grab";
  renderer.domElement.addEventListener("pointerdown", () => {
    controls.autoRotate = false;
    renderer.domElement.style.cursor = "grabbing";
  });
  renderer.domElement.addEventListener("pointerup", () => {
    renderer.domElement.style.cursor = "grab";
  });

  const loop = makeLoop(el, () => { controls.update(); renderer.render(scene, camera); });
  fitRenderer(renderer, camera, mount);
  new ResizeObserver(() => { if (fitRenderer(renderer, camera, mount)) loop.once(); })
    .observe(mount);

  const loader = new GLTFLoader();
  const draco = new DRACOLoader();
  draco.setDecoderPath("vendor/three/addons/libs/draco/gltf/");
  loader.setDRACOLoader(draco);

  let group = null, token = 0, current = -1;

  rail.innerHTML = types.map((t, i) => {
    const col = TYPE_COLOR[t.class] || "#8b94a3";
    return `<button type="button" role="tab" data-i="${i}" style="--cc:${col}"` +
      ` aria-selected="${i === 0}"><s></s><span>${t.label}</span>` +
      `<em>${t.share_pct}%</em></button>`;
  }).join("");

  rail.addEventListener("click", (e) => {
    const b = e.target.closest("[data-i]");
    if (b) select(+b.dataset.i);
  });

  function select(i) {
    if (i === current) return;
    current = i;
    const t = types[i];
    const col = TYPE_COLOR[t.class] || "#8b94a3";
    rail.querySelectorAll("[data-i]").forEach((b) =>
      b.setAttribute("aria-selected", String(+b.dataset.i === i)));
    const btn = rail.querySelector(`[data-i="${i}"]`);
    if (btn) btn.scrollIntoView({ block: "nearest", inline: "nearest" });

    if (status) status.textContent = "Loading";
    const mine = ++token;
    loader.load(t.file, (gltf) => {
      if (mine !== token) { disposeTree(gltf.scene); return; }
      if (group) { scene.remove(group); disposeTree(group); }
      const mesh = gltf.scene.getObjectByProperty("isMesh", true);
      const geo = mesh.geometry;
      geo.computeBoundingBox();
      geo.computeVertexNormals();
      const bb = geo.boundingBox;
      const size = new THREE.Vector3().subVectors(bb.max, bb.min);
      const centre = new THREE.Vector3().addVectors(bb.min, bb.max).multiplyScalar(0.5);
      /* Every cell is drawn the same height whatever its real size, or a
         44 micrometre oligodendrocyte next to a 509 micrometre pyramidal cell
         is a single pixel. The true extent is printed beside it. */
      const s = 2.0 / Math.max(size.x, size.y, size.z);

      const inner = new THREE.Group();
      const solid = new THREE.Mesh(geo, new THREE.MeshStandardMaterial({
        color: new THREE.Color(col), emissive: new THREE.Color(col),
        emissiveIntensity: 0.4, roughness: 0.78, metalness: 0,
        side: THREE.DoubleSide,
      }));
      inner.add(solid);
      solid.position.copy(centre).multiplyScalar(-1);
      /* The block's X is depth, so a raw mesh arrives on its side. */
      inner.rotation.z = Math.PI / 2;
      inner.scale.setScalar(s);
      group = new THREE.Group();
      group.add(inner);
      scene.add(group);
      controls.autoRotate = !REDUCED;
      if (status) status.textContent = "";
      paint(t, geo, col);
      loop.once();
    }, undefined, () => {
      if (mine === token && status) status.textContent = "That mesh did not load.";
    });
  }

  function paint(t, geo, col) {
    if (!info) return;
    const note = NOTES[t.class] || { tag: "", text: "" };
    const faces = geo.index ? geo.index.count / 3 : geo.attributes.position.count / 3;
    const g = groupOf(t.class);
    info.innerHTML =
      `<h3 style="--cc:${col}">${t.label}</h3>` +
      `<p class="tagline">${note.tag}</p>` +
      `<p class="tags"><span class="pill" style="--cc:${col}">${GROUP_LABEL[g]}</span>` +
      `<span class="pill pill-q">${fmt(t.count)} in the block, ${t.share_pct}%</span>` +
      `<span class="pill pill-warn">not proofread</span></p>` +
      `<p class="blurb">${note.text}</p>` +
      `<div class="rows">` +
      `<div><dt>Depth of this class</dt><dd>${fmt(t.depth_um.median)} <u>&micro;m, middle 80% ` +
      `${fmt(t.depth_um.p10)} to ${fmt(t.depth_um.p90)}</u></dd></div>` +
      `<div><dt>This cell's extent</dt><dd>${t.extent_um.map((v) => fmt(v)).join(" &times; ")} <u>&micro;m</u></dd></div>` +
      `<div><dt>Typical for its class</dt><dd>${fmt(t.longest_um)} <u>&micro;m long, sampled ` +
      `${fmt(t.sampled_range_um[0])} to ${fmt(t.sampled_range_um[1])}</u></dd></div>` +
      `<div><dt>Mesh drawn</dt><dd>${fmt(faces)} <u>faces, level ${t.lod}</u></dd></div>` +
      `<div><dt>Soma layer</dt><dd>${t.layer || "unclassified"}</dd></div>` +
      `</div>` +
      `<p class="prov">Segment <code>${t.id}</code> in the c3 agglomeration, ` +
      `chosen as the median of ${Object.keys(t.faces_by_lod).length ? "eleven" : "several"} ` +
      `candidates. Not proofread: it may contain a merge or a split. ` +
      `<a href="${t.neuroglancer}" rel="noopener">Open it in Neuroglancer</a>.</p>`;
  }

  select(0);
  loop.run();
  return { loop, select, types };
}
