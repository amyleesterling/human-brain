/* The 104 proofread cells, one at a time, with the release's own numbers.
 *
 * WHAT IS REAL HERE. Every mesh is pulled from
 * gs://h01-release/data/20210601/proofread_104 and every number beside it is a
 * property of that segment in the release's `segment_properties`, not a
 * measurement of the decimated mesh. Synapse counts, spine counts, spinyness,
 * the length of the axon initial segment: all of it is the reconstruction's,
 * carried across unchanged. The only derived quantities are the volume, which
 * is the release's voxel count times its own 8x8x33 nm voxel, and the soma
 * depth, which is the pia's X minus the soma's X.
 *
 * WHAT IS NOT REAL. The mesh on screen is level of detail 3 of the release's
 * multiresolution mesh, about 22 thousand faces where the full one is 2.7
 * million. The multires levels simplify geometry rather than prune the arbor,
 * so every branch is still there, but the surface is smoother than the
 * microscope saw it. The face count shown is counted off the loaded geometry,
 * so it never claims more than what arrived.
 *
 * ONE STAGE, ONE MESH. 104 meshes is far more than any reader wants at once,
 * so there is a single WebGL context and choosing a cell disposes the last.
 */
import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { DRACOLoader } from "three/addons/loaders/DRACOLoader.js";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import {
  REDUCED, makeRenderer, fitRenderer, makeLoop, studioLights, disposeTree, fmt,
} from "./holo3d.js";

const KLASS_LABEL = {
  pyramidal: "Pyramidal cell",
  interneuron: "Interneuron",
  "spiny-stellate": "Spiny stellate cell",
  "excitatory/spiny-with-atypical-tree": "Spiny cell, atypical tree",
  "unclassified-neuron": "Neuron, unclassified",
  astrocyte: "Astrocyte",
  oligodendrocyte: "Oligodendrocyte",
  "microglia/opc": "Microglia or OPC",
  "blood-vessel-cell": "Blood vessel cell",
  "c-shaped": "C shaped cell",
  "unknown-type": "Unclassified",
};

const KLASS_COLOR = {
  pyramidal: "#3E96F0",
  interneuron: "#B884FF",
  "spiny-stellate": "#7BE4FF",
  "excitatory/spiny-with-atypical-tree": "#5B7CFF",
  "unclassified-neuron": "#A9C6E8",
  astrocyte: "#3FE3B0",
  oligodendrocyte: "#FFB24D",
  "microglia/opc": "#D4FF7E",
  "blood-vessel-cell": "#FF5C7A",
  "c-shaped": "#E27BD8",
  "unknown-type": "#8b94a3",
};

const LAYER_ORDER = ["L1", "L2", "L3", "L4", "L5", "L6", "WM"];

/* Descriptive tags the release carries beyond layer and class. These are the
 * annotator's own words about the shape of the cell, and they are the most
 * interesting thing in the table, so they are surfaced rather than dropped. */
const NOTE_TAGS = {
  "thin-apical-dendrite": "thin apical dendrite",
  bipolar: "bipolar",
  "inverted-apical-dendrite": "inverted apical dendrite",
  "unusually-thin-dendrites": "unusually thin dendrites",
  "sparsely-spiny": "sparsely spiny",
  "lots-of-spines": "lots of spines",
  "possible-interneuron": "possibly an interneuron",
  "web-like-interneuron": "web like interneuron",
  "lot-of-axon": "a lot of axon",
  dark: "dark cytoplasm",
  grey: "grey cytoplasm",
};

export async function mountCells(el) {
  const mount = el.querySelector("[data-mount]");
  const rail = el.querySelector("[data-rail]");
  const status = el.querySelector("[data-status]");
  const facts = el.querySelector("[data-facts]");
  const blurb = el.querySelector("[data-blurb]");
  const ladder = el.querySelector("[data-ladder]");
  if (!mount || !rail) return;

  const db = await fetch("data/cells.json").then((r) => r.json());
  const cells = db.cells.filter((c) => c.mesh);
  cells.sort((a, b) => {
    const la = LAYER_ORDER.indexOf(a.layer), lb = LAYER_ORDER.indexOf(b.layer);
    if (la !== lb) return la - lb;
    return b.NSI - a.NSI;
  });

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(42, 16 / 9, 0.01, 200);
  camera.position.set(0, 0, 2.55);
  const renderer = makeRenderer(mount);
  studioLights(scene, "#3E96F0");

  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;
  controls.enablePan = false;
  controls.minDistance = 0.8;
  controls.maxDistance = 12;
  controls.autoRotate = !REDUCED;
  controls.autoRotateSpeed = 1.1;
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
  /* Size it now, not on the observer's first delivery: a ResizeObserver
     delivers on a rendering step, and a document that is not being rendered
     never has one. See the same note in column.js. */
  fitRenderer(renderer, camera, mount);
  new ResizeObserver(() => {
    if (fitRenderer(renderer, camera, mount)) loop.once();
  }).observe(mount);

  const loader = new GLTFLoader();
  const draco = new DRACOLoader();
  draco.setDecoderPath("vendor/three/addons/libs/draco/gltf/");
  loader.setDRACOLoader(draco);

  let group = null, token = 0, current = -1;

  /* ---- narrowing 104 buttons down to something choosable -----------------
     A flat rail of 104 is a scroll bar with cells in it. Filtering by what a
     cell is, and by which layer it sits in, turns "pick one of 104" into
     "show me the layer 5 pyramidal cells", which is the question a reader
     actually has. Shuffle is for the reader who does not have one. */
  const filterEl = el.querySelector("[data-filter]");
  const shuffleEl = el.querySelector("[data-shuffle]");
  const countEl = el.querySelector("[data-count]");
  let fKlass = "all", fLayer = "all";

  const KLASSES = [...new Set(cells.map((c) => c.klass))]
    .sort((a, b) => cells.filter((c) => c.klass === b).length -
                    cells.filter((c) => c.klass === a).length);
  const LAYERS = LAYER_ORDER.filter((L) => cells.some((c) => c.layer === L));

  const shown = () => cells
    .map((c, i) => ({ c, i }))
    .filter(({ c }) => (fKlass === "all" || c.klass === fKlass) &&
                       (fLayer === "all" || c.layer === fLayer));

  function renderFilters() {
    if (!filterEl) return;
    const chip = (k, v, label, n, col) =>
      `<button type="button" class="chip" data-f="${k}" data-v="${v}"` +
      ` aria-pressed="${(k === "klass" ? fKlass : fLayer) === v}"` +
      (col ? ` style="--cc:${col}"` : "") +
      `>${col ? `<s style="background:${col}"></s>` : ""}${label}` +
      (n == null ? "" : `<em>${n}</em>`) + `</button>`;
    filterEl.innerHTML =
      `<div class="frow"><span class="flab">Kind</span>` +
      chip("klass", "all", "Any", cells.length) +
      KLASSES.map((k) => chip("klass", k, KLASS_LABEL[k] || k,
        cells.filter((c) => c.klass === k).length, KLASS_COLOR[k])).join("") +
      `</div><div class="frow"><span class="flab">Layer</span>` +
      chip("layer", "all", "Any") +
      LAYERS.map((L) => chip("layer", L, L,
        cells.filter((c) => c.layer === L).length)).join("") + `</div>`;
  }

  function renderRail() {
    const list = shown();
    rail.innerHTML = list.map(({ c, i }) => {
      const col = KLASS_COLOR[c.klass] || "#8b94a3";
      return `<button type="button" role="tab" data-i="${i}"` +
        ` aria-selected="${i === current}" style="--cc:${col}">` +
        `<s></s><b>${c.layer || "?"}</b>` +
        `<span>${KLASS_LABEL[c.klass] || c.klass || "cell"}</span>` +
        `<em>${fmt(c.NSI)}</em></button>`;
    }).join("");
    if (countEl) {
      countEl.innerHTML = list.length === cells.length
        ? `All <b>${cells.length}</b> proofread cells.`
        : `<b>${list.length}</b> of ${cells.length} proofread cells.`;
    }
    /* If the current cell was filtered out, move to one that is showing
       rather than leaving the stage on a cell the rail no longer offers. */
    if (list.length && !list.some(({ i }) => i === current)) select(list[0].i);
  }

  if (filterEl) {
    filterEl.addEventListener("click", (e) => {
      const b = e.target.closest("[data-f]");
      if (!b) return;
      if (b.dataset.f === "klass") fKlass = b.dataset.v;
      else fLayer = b.dataset.v;
      renderFilters();
      renderRail();
    });
  }
  if (shuffleEl) {
    shuffleEl.addEventListener("click", () => {
      const list = shown().filter(({ i }) => i !== current);
      if (!list.length) return;
      select(list[Math.floor(Math.random() * list.length)].i, true);
    });
  }

  renderFilters();

  rail.addEventListener("click", (e) => {
    const b = e.target.closest("[data-i]");
    if (b) select(+b.dataset.i);
  });
  rail.addEventListener("keydown", (e) => {
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
    e.preventDefault();
    select((current + (e.key === "ArrowRight" ? 1 : cells.length - 1)) % cells.length, true);
  });

  function select(i, focus) {
    if (i === current) return;
    current = i;
    const c = cells[i];
    const col = KLASS_COLOR[c.klass] || "#8b94a3";

    rail.querySelectorAll("[data-i]").forEach((b) =>
      b.setAttribute("aria-selected", String(+b.dataset.i === i)));
    if (countEl && !rail.querySelector(`[data-i="${i}"]`)) renderRail();
    const btn = rail.querySelector(`[data-i="${i}"]`);
    if (btn) {
      btn.scrollIntoView({ block: "nearest", inline: "nearest" });
      if (focus) btn.focus();
    }

    if (status) status.textContent = "Loading";
    const mine = ++token;

    loader.load(c.mesh, (gltf) => {
      if (mine !== token) { disposeTree(gltf.scene); return; }
      if (group) { scene.remove(group); disposeTree(group); }

      const mesh = gltf.scene.getObjectByProperty("isMesh", true);
      const geo = mesh.geometry;
      geo.computeBoundingBox();
      geo.computeVertexNormals();
      const bb = geo.boundingBox;
      const size = new THREE.Vector3().subVectors(bb.max, bb.min);
      const centre = new THREE.Vector3().addVectors(bb.min, bb.max).multiplyScalar(0.5);

      /* Normalise every cell to the same on screen height so a 4 um blood
         vessel cell and a 900 um pyramidal cell are both worth looking at.
         The real extent is printed beside it, so nothing is being hidden. */
      const longest = Math.max(size.x, size.y, size.z);
      const s = 2.0 / longest;

      const g = new THREE.Group();
      const solid = new THREE.Mesh(geo, new THREE.MeshStandardMaterial({
        color: new THREE.Color(col),
        emissive: new THREE.Color(col), emissiveIntensity: 0.42,
        /* These cells sit in tissue, in water, not in air. A specular
           highlight reads as wet plastic, so the surface is kept rough and
           the shape is carried by the emissive and the rim light instead. */
        roughness: 0.78, metalness: 0.0,
        /* A dendrite a pixel or two wide loses most of its far wall to
           backface culling, and the arbor thins out to nothing. */
        side: THREE.DoubleSide,
      }));
      g.add(solid);
      /* The volume's X is depth and its Y is tangential, so the mesh arrives
         lying on its side. Rotating it puts the pia up, which is the only
         orientation these cells are ever drawn in. */
      g.rotation.z = Math.PI / 2;
      g.scale.setScalar(s);
      solid.position.copy(centre).multiplyScalar(-1);

      group = new THREE.Group();
      group.add(g);
      scene.add(group);
      controls.autoRotate = !REDUCED;
      if (status) status.textContent = "";

      const faces = geo.index ? geo.index.count / 3 : geo.attributes.position.count / 3;
      paint(c, size, faces, col);
      loop.once();
    }, undefined, () => {
      if (mine === token && status) status.textContent = "That mesh did not load.";
    });
  }

  function paint(c, size, faces, col) {
    if (blurb) {
      const notes = c.tags.filter((t) => NOTE_TAGS[t]).map((t) => NOTE_TAGS[t]);
      blurb.innerHTML =
        `<span class="pill" style="--cc:${col}">${KLASS_LABEL[c.klass] || "cell"}</span>` +
        (c.soma_layer ? ` <span class="pill pill-q">${c.soma_layer}</span>` : "") +
        (notes.length ? ` <span class="notes">${notes.join(", ")}</span>` : "") +
        `<div class="segid">segment <code>${c.id}</code></div>`;
    }

    if (facts) {
      /* Only what the release actually carries for this cell. A blood vessel
         cell has no spines and no axon initial segment, and printing a zero
         for something that was never measured would be a claim. */
      const rows = [];
      const add = (k, v, u) => rows.push([k, v, u || ""]);
      /* "below the surface", not "below the pia". The reference is the outward
         face of the release's layer 1 region, which is close to the pial
         surface but is not measured as it. */
      if (c.soma_depth_um != null) {
        add("Soma depth", fmt(c.soma_depth_um), "&micro;m below the surface");
      }
      add("Reconstructed volume", fmt(c.volume_um3), "&micro;m<sup>3</sup>");
      add("Extent", `${fmt(size.x)} &times; ${fmt(size.y)} &times; ${fmt(size.z)}`, "&micro;m");
      add("Incoming synapses", fmt(c.NSI));
      if (c.NSI > 0) {
        add("&nbsp;&nbsp;excitatory", `${fmt(c.NSIe)} <em>${Math.round(100 * c.NSIe / c.NSI)}%</em>`);
        add("&nbsp;&nbsp;inhibitory", `${fmt(c.NSIi)} <em>${Math.round(100 * c.NSIi / c.NSI)}%</em>`);
      }
      add("Outgoing synapses", fmt(c.NSO));
      add("Dendrite nodes", fmt(c.NDe));
      add("Axon nodes", fmt(c.NAx));
      if (c.NSp > 0) add("Spine nodes", fmt(c.NSp));
      if (c.NDe > 0) add("Spinyness", c.Sp.toFixed(3), "spines per dendrite node");
      if (c.NAis > 0) add("Axon initial segment", fmt(c.NAis), "nodes");
      if (c.NMy > 0) add("Myelinated axon", fmt(c.NMy), "nodes");
      if (c.NCi > 0) add("Cilium", fmt(c.NCi), "nodes");
      add("Mesh drawn", fmt(faces), "faces, level of detail 3");

      facts.innerHTML = rows.map(([k, v, u]) =>
        `<div class="f"><dt>${k}</dt><dd>${v}${u ? ` <u>${u}</u>` : ""}</dd></div>`).join("");
    }

    if (ladder && c.soma_depth_um != null) {
      /* Where this cell's soma sits in the depth of the volume. The bands are
         the release's own layers, measured as the middle 90 per cent of each
         layer's cell bodies, so the ladder is drawn from the same table the
         marker is placed on and the two cannot drift apart. The scale is
         linear in micrometres: a layer 5 cell reads as genuinely deep rather
         than as a tick on an arbitrary axis. */
      const maxd = db.cortex_depth_um;
      const pct = Math.max(0, Math.min(100, 100 * c.soma_depth_um / maxd));
      ladder.innerHTML =
        `<div class="lad"><div class="lad-rail">` +
        db.layer_bands.filter((b) => b.reliable !== false).map((b) =>
          `<i style="top:${100 * b.top_um / maxd}%;` +
          `height:${100 * (b.bottom_um - b.top_um) / maxd}%"` +
          ` title="${b.layer}"><u>${b.layer.replace("Layer ", "L")
            .replace("White matter", "WM")}</u></i>`).join("") +
        `<b style="top:${pct}%;--cc:${col}"></b></div>` +
        `<div class="lad-lab"><span>the surface</span>` +
        `<span><b>${fmt(c.soma_depth_um)}</b> &micro;m deep</span>` +
        `<span>${fmt(maxd)} &micro;m</span></div></div>`;
    } else if (ladder) {
      ladder.innerHTML = "";
    }
  }

  renderRail();
  select(0);
  loop.run();
  return { loop, select, cells };
}
