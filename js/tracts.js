/* The white matter, and a signal running through it.
 *
 * WHAT IS REAL HERE. Every streamline is from the HCP1065 population-averaged
 * tractography atlas, 87 named bundles averaged over 1,065 Human Connectome
 * Project subjects (Yeh, Nat Commun 13:4933, 2022, CC-BY-SA 4.0). The cortical
 * surface is the HCP S1200 group average, fs_LR 32k, MSMAll registered. The
 * two are brought into one space by the affine in the tractography's own file
 * header, and scripts/fetch_hcp.py refuses to write the data at all unless the
 * left corticospinal tract comes out on the left running brainstem to vertex,
 * the left arcuate comes out arching frontal to temporal, and the corpus
 * callosum crosses the midline.
 *
 * WHAT THE ANIMATION IS. Not decoration, and not a guess. Each vertex carries
 * how far along its own streamline it sits, in millimetres, measured from the
 * real geometry. The shader turns that into an arrival time by dividing by a
 * conduction velocity you choose. So a long tract genuinely takes longer than
 * a short one, in the correct ratio, and changing the velocity changes every
 * transit time in the scene at once. The number printed beside a bundle is
 * that division done on its real median length.
 *
 * WHAT IT IS NOT. Tractography is an inference from how water diffuses, not a
 * picture of axons. These are the paths a reconstruction algorithm found in a
 * population average. They are not the 1,065 people's actual fibres, and no
 * tractogram distinguishes which direction a bundle carries signal.
 */
import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { DRACOLoader } from "three/addons/loaders/DRACOLoader.js";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { REDUCED, makeRenderer, fitRenderer, makeLoop, fmt } from "./holo3d.js";

const GROUP_COLOR = {
  "Association": "#3E96F0",
  "Projection": "#FFB24D",
  "Commissural": "#B884FF",
  "Cerebellum": "#3FE3B0",
  "Cranial nerve": "#FF5C7A",
};

/* The named bundles worth calling out by name, because an acronym list is not
 * a page. Everything not in here still draws and still labels with its
 * atlas id; this only adds English where there is English to add. */
const NAMED = {
  AF: "Arcuate fasciculus", CST: "Corticospinal tract", CC: "Corpus callosum",
  AC: "Anterior commissure", IFOF: "Inferior fronto-occipital fasciculus",
  ILF: "Inferior longitudinal fasciculus", UF: "Uncinate fasciculus",
  OR: "Optic radiation", AR: "Acoustic radiation", F: "Fornix",
  ML: "Medial lemniscus", MCP: "Middle cerebellar peduncle",
  SCP: "Superior cerebellar peduncle", ICP: "Inferior cerebellar peduncle",
  VOF: "Vertical occipital fasciculus", FAT: "Frontal aslant tract",
  MdLF: "Middle longitudinal fasciculus", EMC: "Extreme capsule",
  SLF1: "Superior longitudinal fasciculus I",
  SLF2: "Superior longitudinal fasciculus II",
  SLF3: "Superior longitudinal fasciculus III",
  CBT: "Corticobulbar tract", RST: "Rubrospinal tract",
  DRTT: "Dentatorubrothalamic tract", CB: "Cerebellum",
  CNII: "Optic nerve", CNIII: "Oculomotor nerve", CNV: "Trigeminal nerve",
  CNVII: "Facial nerve", CNVIII: "Vestibulocochlear nerve",
};

function stemOf(id) {
  return id.replace(/_(L|R)$/, "");
}

function prettyName(id) {
  const m = /^([A-Za-z_0-9]+?)(_[LR])?$/.exec(id);
  const stem = m ? m[1] : id;
  const side = m && m[2] ? (m[2] === "_L" ? " (left)" : " (right)") : "";
  const base = NAMED[stem] || NAMED[stem.split("_")[0]];
  return (base ? base : id.replace(/_/g, " ")) + side;
}

/* Conduction velocities that actually occur in human white matter. The slow
 * end is unmyelinated fibre, the fast end the largest myelinated ones. */
const SPEEDS = [
  { v: 1, label: "1 m/s", note: "unmyelinated" },
  { v: 10, label: "10 m/s", note: "thinly myelinated" },
  { v: 60, label: "60 m/s", note: "typical large myelinated fibre" },
  { v: 120, label: "120 m/s", note: "the fastest in the body" },
];

const VERT = `
attribute float cum;      // millimetres along this streamline
attribute vec3 acolor;
attribute float bundle;
attribute float chOn;     // 1 if this bundle is in the chosen chain
attribute float chOff;    // millimetres of chain already travelled before it
uniform float uChain;     // 1 while a chain is chosen
uniform float uBundle;    // -1 for all
uniform float vmm;        // conduction velocity, mm per second
uniform float slow;       // how many times slower than real this is shown
uniform float time;
uniform float period;
uniform float pulse;      // 0 = no pulse, static lines
varying vec3 vcolor;
varying float vlit;
varying float vdrop;
void main() {
  vcolor = acolor;
  vdrop = (uBundle < 0.0 || abs(bundle - uBundle) < 0.5) ? 0.0 : 1.0;
  // A chain hides everything not in it, and gives each leg a head start equal
  // to the length of the legs before it, so one pulse runs the whole route in
  // order instead of every leg firing at once.
  if (uChain > 0.5) vdrop = chOn > 0.5 ? 0.0 : 1.0;
  float lead = uChain > 0.5 ? chOff : 0.0;
  // Arrival time at this point, from the real distance along the real
  // streamline divided by the chosen velocity. This is the whole physics.
  // The slow factor stretches the clock and nothing else: it cannot change
  // the ratio between two tracts, only how long you get to watch it.
  float arrival = ((cum + lead) / vmm) * slow;
  float g = fract((time - arrival) / period);
  // a short bright head with a tail behind it
  float head = smoothstep(0.10, 0.0, g) + 0.35 * smoothstep(0.30, 0.05, g);
  vlit = mix(1.0, head, pulse);
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}`;

const FRAG = `
varying vec3 vcolor;
varying float vlit;
varying float vdrop;
uniform float base;
uniform float dim;
void main() {
  if (vdrop > 0.5) discard;
  gl_FragColor = vec4(vcolor * (base + vlit), dim * (base + vlit) * 0.9);
}`;

export async function mountTracts(el) {
  const mount = el.querySelector("[data-mount]");
  const status = el.querySelector("[data-status]");
  const groupsEl = el.querySelector("[data-groups]");
  const bundleEl = el.querySelector("[data-bundles]");
  const surfEl = el.querySelector("[data-surface]");
  const speedEl = el.querySelector("[data-speed]");
  const infoEl = el.querySelector("[data-info]");
  if (!mount) return;

  if (status) status.textContent = "Loading 87 white matter bundles";
  const meta = await fetch("data/tracts.json").then((r) => r.json());
  const buf = await fetch(meta.bin).then((r) => r.arrayBuffer());
  const surfMeta = await fetch("data/surface.json").then((r) => r.json());
  /* What each bundle is for, and a few ordinary actions written as chains of
     real bundles. The timings in it are arithmetic on the same median lengths
     this page already draws. */
  const paths = await fetch("data/pathways.json").then((r) => r.json())
    .catch(() => ({ descriptions: {}, actions: [] }));

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(40, 16 / 9, 1, 4000);
  /* MNI is a right anterior superior frame: x is left to right, y is back to
     front, and Z IS UP. three.js assumes Y is up, so leaving this alone draws
     the brain lying on its back with the nose pointing at the ceiling, and
     orbiting it spins around the wrong axis so a lateral view is unreachable.
     Telling the camera that up is +Z fixes both: OrbitControls builds its
     rotation from object.up, so the drag then behaves the way the anatomy
     says it should. */
  camera.up.set(0, 0, 1);
  const renderer = makeRenderer(mount);

  /* ---- the tracts -------------------------------------------------------
     One geometry for all 87 bundles. 18,122 streamlines at 28 points each is
     489,258 line segments, which is one draw call and no per-bundle state; a
     bundle is hidden by an attribute the shader reads, not by a second mesh. */
  const K = meta.bundles[0].points_per_line;
  const totalLines = meta.bundles.reduce((s, b) => s + b.lines, 0);
  const segs = totalLines * (K - 1);
  const pos = new Float32Array(segs * 2 * 3);
  const cum = new Float32Array(segs * 2);
  const col = new Float32Array(segs * 2 * 3);
  const bid = new Float32Array(segs * 2);

  const centre = new THREE.Vector3();
  let w = 0, nv = 0;
  meta.bundles.forEach((b, bi) => {
    const c = new THREE.Color(GROUP_COLOR[b.group] || "#8b94a3");
    const q = new Int16Array(buf, b.offset, b.lines * K * 3);
    for (let l = 0; l < b.lines; l++) {
      let run = 0;
      const o = l * K * 3;
      for (let k = 0; k < K - 1; k++) {
        const a0 = o + k * 3, a1 = o + (k + 1) * 3;
        const x0 = q[a0] / meta.scale, y0 = q[a0 + 1] / meta.scale, z0 = q[a0 + 2] / meta.scale;
        const x1 = q[a1] / meta.scale, y1 = q[a1 + 1] / meta.scale, z1 = q[a1 + 2] / meta.scale;
        const d = Math.hypot(x1 - x0, y1 - y0, z1 - z0);
        pos[w] = x0; pos[w + 1] = y0; pos[w + 2] = z0;
        pos[w + 3] = x1; pos[w + 4] = y1; pos[w + 5] = z1;
        col[w] = c.r; col[w + 1] = c.g; col[w + 2] = c.b;
        col[w + 3] = c.r; col[w + 4] = c.g; col[w + 5] = c.b;
        cum[nv] = run; cum[nv + 1] = run + d;
        bid[nv] = bi; bid[nv + 1] = bi;
        run += d;
        w += 6; nv += 2;
      }
    }
  });

  const geom = new THREE.BufferGeometry();
  geom.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  geom.setAttribute("acolor", new THREE.BufferAttribute(col, 3));
  geom.setAttribute("cum", new THREE.BufferAttribute(cum, 1));
  geom.setAttribute("bundle", new THREE.BufferAttribute(bid, 1));
  const chOn = new Float32Array(segs * 2);
  const chOff = new Float32Array(segs * 2);
  geom.setAttribute("chOn", new THREE.BufferAttribute(chOn, 1));
  geom.setAttribute("chOff", new THREE.BufferAttribute(chOff, 1));
  geom.computeBoundingSphere();
  centre.copy(geom.boundingSphere.center);

  const mat = new THREE.ShaderMaterial({
    vertexShader: VERT, fragmentShader: FRAG,
    uniforms: {
      time: { value: 0 }, vmm: { value: 60000 }, period: { value: 2.4 },
      /* A real impulse crosses the whole corticospinal tract in 2.2 ms. Shown
         at life speed the entire white matter would flash at once and there
         would be nothing to see, so the clock is stretched by a fixed factor
         and the page says so. The factor is the same for every tract and every
         velocity, so every ratio on screen is still the real one. */
      slow: { value: 300 },
      pulse: { value: REDUCED ? 0 : 1 }, uBundle: { value: -1 },
      uChain: { value: 0 },
      /* 489,258 additively blended segments stacked over one brain sum
         straight to white, and a saturated scene cannot show a pulse at all:
         measured, the lit fraction moved by 0.01 per cent across a whole
         cycle. These two were set by reading the framebuffer back until the
         resting state was dim and the pulse had somewhere to go. */
      base: { value: 0.09 }, dim: { value: 0.16 },
    },
    transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
  });
  const lines = new THREE.LineSegments(geom, mat);
  scene.add(lines);

  /* ---- the cortex -------------------------------------------------------
     A glass shell around the tracts. FrontSide with depthWrite off, or a
     translucent surface culls everything it contains. */
  const loader = new GLTFLoader();
  const draco = new DRACOLoader();
  draco.setDecoderPath("vendor/three/addons/libs/draco/gltf/");
  loader.setDRACOLoader(draco);

  const cortex = new THREE.Group();
  scene.add(cortex);
  const hemis = {};
  const NV = surfMeta.surface.vertices_per_hemisphere;
  let labelBuf = null;

  /* Lambert, not Basic. An unlit surface is a flat silhouette: the gyri and
     sulci vanish and a tinted parcellation reads as a smear of colour with no
     shape under it, which is what made the first version hard to look at.
     Two lights and a rim give it form without making it shiny, and the cortex
     is wet tissue rather than plastic so there is no specular here at all. */
  const surfMat = () => new THREE.MeshLambertMaterial({
    color: 0x9fc4e8, transparent: true, opacity: 0.075,
    side: THREE.FrontSide, depthWrite: false, blending: THREE.AdditiveBlending,
    vertexColors: false, emissive: 0x0a1420,
  });
  scene.add(new THREE.AmbientLight(0xffffff, 1.35));
  const key = new THREE.DirectionalLight(0xffffff, 1.15);
  key.position.set(-500, -260, 420);
  scene.add(key);
  const rim = new THREE.DirectionalLight(0x9fd0ff, 0.75);
  rim.position.set(420, 300, -260);
  scene.add(rim);

  await Promise.all(["L", "R"].map((h) => new Promise((res) => {
    loader.load(surfMeta.surface.mesh[h], (g) => {
      const m = g.scene.getObjectByProperty("isMesh", true);
      if (!m) return res();
      /* The exported GLB carries POSITION only. Without normals a Lambert
         surface is shaded per face, so 64,980 triangles read as 64,980 flat
         facets and the cortex looks far coarser than it is. The mesh was
         never the problem; the missing normals were. */
      m.geometry.computeVertexNormals();
      const mesh = new THREE.Mesh(m.geometry, surfMat());
      mesh.renderOrder = 2;
      hemis[h] = mesh;
      cortex.add(mesh);
      res();
    }, undefined, () => res());
  })));

  labelBuf = await fetch(surfMeta.bin).then((r) => r.arrayBuffer());

  const controls = new OrbitControls(camera, renderer.domElement);
  controls.target.copy(centre);
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;
  controls.enablePan = false;
  controls.minDistance = 120;
  controls.maxDistance = 900;
  controls.autoRotate = !REDUCED;
  controls.autoRotateSpeed = 0.5;
  renderer.domElement.style.cursor = "grab";
  renderer.domElement.addEventListener("pointerdown", () => {
    controls.autoRotate = false;
    renderer.domElement.style.cursor = "grabbing";
  });
  renderer.domElement.addEventListener("pointerup", () => {
    renderer.domElement.style.cursor = "grab";
  });
  /* Named viewpoints, in MNI, so "show me the side" is one tap rather than a
     drag you have to get lucky with. Anatomy is always drawn from one of
     these, and hunting for them by orbiting is the thing that made this panel
     frustrating to use. */
  const VIEWS = {
    left: { v: [-1, -0.13, 0.16], label: "Left" },
    right: { v: [1, -0.13, 0.16], label: "Right" },
    front: { v: [0.05, 1, 0.14], label: "Front" },
    back: { v: [0.05, -1, 0.14], label: "Back" },
    top: { v: [0.02, -0.1, 1], label: "Top" },
  };
  /* Measured off the framebuffer: at 430 the brain filled 44 per cent of the
     canvas height with a quarter of the frame empty above and below. The
     scene is about 180 mm across and the field of view is 40 degrees, so this
     puts it at roughly four fifths of the height. */
  const DIST = 268;
  function setView(k, animate) {
    const v = VIEWS[k] || VIEWS.left;
    const d = new THREE.Vector3(...v.v).normalize().multiplyScalar(DIST);
    camera.position.copy(centre).add(d);
    controls.target.copy(centre);
    /* A viewpoint the reader asked for should stay where they put it. */
    controls.autoRotate = false;
    controls.update();
    loop.once();
  }
  controls.autoRotateSpeed = 0.42;

  const loop = makeLoop(el, (dt) => {
    mat.uniforms.time.value += dt;
    controls.update();
    renderer.render(scene, camera);
  });
  fitRenderer(renderer, camera, mount);
  new ResizeObserver(() => {
    if (fitRenderer(renderer, camera, mount)) loop.once();
  }).observe(mount);

  /* ---- surface colouring ------------------------------------------------ */
  let surfMode = "off";
  /* How solid the cortex is drawn. A tint you cannot see is not a tint, and a
     cortex you cannot see through hides the tracts, so this is the reader's
     choice rather than one number picked for them. */
  const VEIL = { ghost: 0.30, mid: 0.62, solid: 0.94 };
  let veil = "mid";

  function paintSurface() {
    const set = surfMeta.sets[surfMode];
    ["L", "R"].forEach((h, hi) => {
      const mesh = hemis[h];
      if (!mesh) return;
      if (!set) {
        /* Untinted, the shell is barely there and additive is right: it reads
           as a faint glow around the tracts rather than a wall in front of
           them. */
        mesh.material.vertexColors = false;
        mesh.material.color.setHex(0x9fc4e8);
        mesh.material.opacity = 0.075;
        mesh.material.blending = THREE.AdditiveBlending;
        mesh.material.depthWrite = false;
        mesh.geometry.deleteAttribute("color");
        mesh.material.needsUpdate = true;
        return;
      }
      const lab = new Uint16Array(labelBuf, set.offset + hi * NV * 2, NV);
      const c = new Float32Array(NV * 3);
      for (let i = 0; i < NV; i++) {
        const v = lab[i];
        /* Label 0 is the medial wall, which is not a network and must not be
           given a colour as though it were one. */
        const col3 = v === 0 ? [0.10, 0.12, 0.16] : labelColor(v, set);
        c[i * 3] = col3[0]; c[i * 3 + 1] = col3[1]; c[i * 3 + 2] = col3[2];
      }
      mesh.geometry.setAttribute("color", new THREE.BufferAttribute(c, 3));
      mesh.material.vertexColors = true;
      mesh.material.color.setHex(0xffffff);
      /* A tinted shell has to be a skin, not a lamp. Additively blended at
         this opacity it sums with every tract behind it and the whole brain
         goes white: measured, 2.2 per cent of the frame was fully saturated.
         Normal blending lets it sit in front of the tracts and be seen
         through, which is what a translucent surface actually does. */
      mesh.material.blending = THREE.NormalBlending;
      mesh.material.opacity = VEIL[veil];
      /* A translucent surface must not write depth or it culls the tracts it
         contains, but at full opacity it should, or the far wall of the brain
         shows through the near one and the folds stop reading. */
      mesh.material.depthWrite = veil === "solid";
      mesh.material.needsUpdate = true;
    });
    loop.once();
  }

  /* Distinct hues around the wheel. The Yeo networks have canonical colours in
     their own label tables, but those tables are not carried in the packed
     binary, so this generates a stable, evenly spaced set instead and says so
     rather than pretending to be the published palette. */
  function labelColor(v, set) {
    const n = Math.max(2, set.n_regions);
    const h = (v * 0.6180339887) % 1;
    const c = new THREE.Color().setHSL(h, n > 40 ? 0.55 : 0.62, n > 40 ? 0.55 : 0.6);
    return [c.r, c.g, c.b];
  }

  /* ---- controls ---------------------------------------------------------- */
  let activeGroup = "all", activeBundle = -1;

  function bundleList() {
    return meta.bundles
      .map((b, i) => ({ ...b, i }))
      .filter((b) => activeGroup === "all" || b.group === activeGroup);
  }

  function renderBundles() {
    if (!bundleEl) return;
    bundleEl.innerHTML = bundleList().map((b) =>
      `<button type="button" class="lg" data-b="${b.i}"` +
      ` aria-pressed="${activeBundle === b.i}"` +
      ` style="--cc:${GROUP_COLOR[b.group]}"><s style="background:${GROUP_COLOR[b.group]}"></s>` +
      `<span>${prettyName(b.id)}</span><em>${fmt(b.length_mm.median)} mm</em></button>`
    ).join("");
  }

  /* Keep roughly one pulse in flight. The longest tract on screen decides how
     long a cycle has to be; without this, a slow velocity puts a dozen bands
     on one tract at once and a fast one leaves the scene empty most of the
     time. This changes only how often the pulse repeats, never how fast it
     travels, which is the part that is a measurement. */
  function retime() {
    const vis = bundleList();
    const longest = action
      ? action.total_mm
      : activeBundle >= 0
        ? meta.bundles[activeBundle].length_mm.p95
        : Math.max(...vis.map((b) => b.length_mm.p95));
    const shown = (longest / mat.uniforms.vmm.value) * mat.uniforms.slow.value;
    mat.uniforms.period.value = Math.min(9, Math.max(1.4, shown * 1.45));
  }

  function showInfo() {
    if (!infoEl) return;
    const v = mat.uniforms.vmm.value / 1000;
    const slow = mat.uniforms.slow.value;
    if (activeBundle < 0) {
      const tot = meta.bundles.reduce((s, b) => s + b.streamlines_in_atlas, 0);
      infoEl.innerHTML =
        `<b>${meta.bundles.length}</b> named bundles from <b>${fmt(meta.subjects)}</b> ` +
        `people. The atlas holds ${fmt(tot)} streamlines; this page draws ` +
        `${fmt(totalLines)} of them. Pick one to see how long a signal takes to cross it.`;
      return;
    }
    const b = meta.bundles[activeBundle];
    const ms = (L) => (L / (v * 1000)) * 1000;
    infoEl.innerHTML =
      `<b>${prettyName(b.id)}</b> <span class="pill" style="--cc:${GROUP_COLOR[b.group]}">${b.group}</span>` +
      `<div class="rows">` +
      `<div><dt>Median length</dt><dd>${fmt(b.length_mm.median)} <u>mm</u></dd></div>` +
      `<div><dt>Range, 5th to 95th</dt><dd>${fmt(b.length_mm.p5)} to ${fmt(b.length_mm.p95)} <u>mm</u></dd></div>` +
      `<div><dt>Streamlines in the atlas</dt><dd>${fmt(b.streamlines_in_atlas)}</dd></div>` +
      `<div><dt>Drawn here</dt><dd>${fmt(b.lines)}</dd></div>` +
      `<div><dt>Crossing time at ${v} m/s</dt><dd>${ms(b.length_mm.median).toFixed(ms(b.length_mm.median) < 10 ? 2 : 1)} <u>ms</u></dd></div>` +
      `</div>` +
      (paths.descriptions[stemOf(b.id)]
        ? `<p class="whatfor">${paths.descriptions[stemOf(b.id)]}</p>` : "") +
      `<p class="slowline">Shown <b>${fmt(slow)} times slower</b> than real. ` +
      `At life speed this crossing would be over before the screen had ` +
      `finished drawing one frame.</p>`;
  }

  if (groupsEl) {
    const gs = ["all", ...Object.keys(GROUP_COLOR)];
    groupsEl.innerHTML = gs.map((g, i) =>
      `<button type="button" role="tab" data-g="${g}" aria-selected="${i === 0}">` +
      `${g === "all" ? "Every bundle" : g}</button>`).join("");
    groupsEl.addEventListener("click", (e) => {
      const b = e.target.closest("[data-g]");
      if (!b) return;
      activeGroup = b.dataset.g;
      activeBundle = -1;
      mat.uniforms.uBundle.value = -1;
      groupsEl.querySelectorAll("[data-g]").forEach((x) =>
        x.setAttribute("aria-selected", String(x === b)));
      renderBundles(); retime(); showInfo(); loop.once();
    });
  }

  if (bundleEl) {
    bundleEl.addEventListener("click", (e) => {
      const b = e.target.closest("[data-b]");
      if (!b) return;
      const i = +b.dataset.b;
      if (action) {
        action = null;
        if (actEl) actEl.querySelectorAll("[data-a]").forEach((x) =>
          x.setAttribute("aria-selected", String(x.dataset.a === "none")));
        applyChain();
      }
      activeBundle = activeBundle === i ? -1 : i;
      mat.uniforms.uBundle.value = activeBundle;
      /* One bundle on its own is a hundredth of the ink, so it has to be
         drawn brighter or selecting a tract looks like turning it off. */
      mat.uniforms.dim.value = activeBundle < 0 ? 0.16 : 0.75;
      renderBundles(); retime(); showInfo(); loop.once();
    });
  }

  if (surfEl) {
    const opts = [["off", "No surface tint"],
                  ["yeo7", "Resting state networks, 7"],
                  ["yeo17", "Resting state networks, 17"],
                  ["glasser", "HCP-MMP1, 360 regions"]];
    surfEl.innerHTML = opts.map(([k, l], i) =>
      `<button type="button" role="tab" data-s="${k}" aria-selected="${i === 0}">${l}</button>`).join("");
    surfEl.addEventListener("click", (e) => {
      const b = e.target.closest("[data-s]");
      if (!b) return;
      surfMode = b.dataset.s;
      surfEl.querySelectorAll("[data-s]").forEach((x) =>
        x.setAttribute("aria-selected", String(x === b)));
      paintSurface();
    });
  }

  /* ---- actions -----------------------------------------------------------
     An ordinary thing a person does, written as a chain of real bundles. The
     scene shows only that chain, each leg tinted along the sequence, and the
     pulse walks the whole chain end to end with each leg starting where the
     last one finished. The arithmetic is on the same measured lengths the
     rest of the page uses. */
  const actEl = el.querySelector("[data-actions]");
  const actInfoEl = el.querySelector("[data-actinfo]");
  let action = null;

  /* One geometry holds every bundle, so a chain is drawn by allowing several
     bundle ids at once and giving each an offset so the pulse runs through
     them in order rather than all at the same time. */
  const perBundleOn = new Float32Array(meta.bundles.length);
  const perBundleOff = new Float32Array(meta.bundles.length);

  function applyChain() {
    perBundleOn.fill(0);
    perBundleOff.fill(0);
    if (action) {
      let run = 0;
      action.steps.forEach((st) => {
        const i = meta.bundles.findIndex((b) => b.id === st.tract);
        if (i < 0) return;
        perBundleOn[i] = 1;
        perBundleOff[i] = run;
        run += st.length_mm;
      });
      mat.uniforms.uChain.value = 1;
      mat.uniforms.dim.value = 0.9;
    } else {
      mat.uniforms.uChain.value = 0;
      mat.uniforms.dim.value = activeBundle < 0 ? 0.16 : 0.75;
    }
    /* One pass over the vertices rather than a texture lookup per fragment.
       This runs on a click, not on a frame. */
    for (let i = 0; i < chOn.length; i++) {
      const b = bid[i];
      chOn[i] = perBundleOn[b];
      chOff[i] = perBundleOff[b];
    }
    geom.attributes.chOn.needsUpdate = true;
    geom.attributes.chOff.needsUpdate = true;
    retime();
    showAction();
    loop.once();
  }

  function showAction() {
    if (!actInfoEl) return;
    if (!action) { actInfoEl.innerHTML = ""; return; }
    const v = mat.uniforms.vmm.value / 1000;
    const t = action.timing[String(v)] || action.timing["60"];
    actInfoEl.innerHTML =
      `<p class="actblurb">${action.blurb}</p>` +
      `<ol class="chain">` + action.steps.map((st, i) =>
        `<li style="--cc:${GROUP_COLOR[st.group] || "#8b94a3"}">` +
        `<b>${prettyName(st.tract)}</b><span>${st.what}</span>` +
        `<em>${fmt(st.length_mm)} mm</em></li>`).join("") + `</ol>` +
      `<div class="rows">` +
      `<div><dt>Total cable</dt><dd>${fmt(action.total_mm)} <u>mm</u></dd></div>` +
      `<div><dt>Travel at ${v} m/s</dt><dd>${t.travel_ms} <u>ms</u></dd></div>` +
      `<div><dt>${action.relays} synapses on the way</dt><dd>${t.synapses_ms} <u>ms</u></dd></div>` +
      `<div><dt>All in</dt><dd><b>${t.total_ms}</b> <u>ms</u></dd></div>` +
      `</div>` +
      `<p class="tnote">At this speed the synapses are <b>${t.synapses_share_pct}%</b> ` +
      `of the delay. Crossing a synapse costs about a millisecond however fast ` +
      `the cable is, so the faster the fibre, the more of the wait is the gaps ` +
      `rather than the wire.</p>`;
  }

  if (actEl && paths.actions.length) {
    actEl.innerHTML =
      `<button type="button" role="tab" data-a="none" aria-selected="true">` +
      `Just the anatomy</button>` +
      paths.actions.map((a) =>
        `<button type="button" role="tab" data-a="${a.id}"` +
        ` aria-selected="false">${a.name}</button>`).join("");
    actEl.addEventListener("click", (e) => {
      const b = e.target.closest("[data-a]");
      if (!b) return;
      action = b.dataset.a === "none"
        ? null : paths.actions.find((a) => a.id === b.dataset.a);
      actEl.querySelectorAll("[data-a]").forEach((x) =>
        x.setAttribute("aria-selected", String(x === b)));
      /* A chain overrides any single bundle the reader had picked, or the two
         filters fight and the scene shows neither. */
      if (action) {
        activeBundle = -1;
        mat.uniforms.uBundle.value = -1;
        renderBundles();
        showInfo();
      }
      applyChain();
    });
  }

  const viewEl = el.querySelector("[data-view]");
  if (viewEl) {
    viewEl.innerHTML = Object.entries(VIEWS).map(([k, v], i) =>
      `<button type="button" role="tab" data-view-k="${k}"` +
      ` aria-selected="${i === 0}">${v.label}</button>`).join("") +
      `<button type="button" data-spin>Spin</button>`;
    viewEl.addEventListener("click", (e) => {
      const b = e.target.closest("[data-view-k]");
      if (b) {
        setView(b.dataset.viewK);
        viewEl.querySelectorAll("[data-view-k]").forEach((x) =>
          x.setAttribute("aria-selected", String(x === b)));
        return;
      }
      if (e.target.closest("[data-spin]")) {
        controls.autoRotate = !controls.autoRotate;
        e.target.closest("[data-spin]")
          .setAttribute("aria-selected", String(controls.autoRotate));
      }
    });
  }

  const veilEl = el.querySelector("[data-veil]");
  if (veilEl) {
    veilEl.innerHTML = [["ghost", "Ghost"], ["mid", "Translucent"],
                        ["solid", "Solid"]].map(([k, l]) =>
      `<button type="button" role="tab" data-veil-k="${k}"` +
      ` aria-selected="${k === veil}">${l}</button>`).join("");
    veilEl.addEventListener("click", (e) => {
      const b = e.target.closest("[data-veil-k]");
      if (!b) return;
      veil = b.dataset.veilK;
      veilEl.querySelectorAll("[data-veil-k]").forEach((x) =>
        x.setAttribute("aria-selected", String(x === b)));
      paintSurface();
    });
  }

  if (speedEl) {
    speedEl.innerHTML = SPEEDS.map((s, i) =>
      `<button type="button" role="tab" data-v="${s.v}" aria-selected="${s.v === 60}">` +
      `${s.label}<u>${s.note}</u></button>`).join("");
    speedEl.addEventListener("click", (e) => {
      const b = e.target.closest("[data-v]");
      if (!b) return;
      mat.uniforms.vmm.value = +b.dataset.v * 1000;
      retime();
      showAction();
      speedEl.querySelectorAll("[data-v]").forEach((x) =>
        x.setAttribute("aria-selected", String(x === b)));
      showInfo(); loop.once();
    });
  }

  setView("left");
  renderBundles();
  retime();
  showInfo();
  paintSurface();
  if (status) status.textContent = "";
  loop.run();
  return { loop, meta, mat, camera, controls, scene };
}
