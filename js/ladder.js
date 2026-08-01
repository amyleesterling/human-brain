/* One push from Earth to a single synapse in one human brain.
 *
 * WHAT IS REAL. Every stage is a real photograph or a real measurement: NASA
 * and USGS imagery down to a street in Boston, an anatomical atlas for the
 * body, BigBrain for the tissue, the H01 cubic millimetre with all 49,379 of
 * its cell bodies, one hand-proofread layer 5 pyramidal cell, and one synapse
 * out of the electron microscopy. The field of view printed at every moment is
 * the real size of the real object, not a caption.
 *
 * EVERY STEP ZOOMS IN. The build script asserts it. An earlier version put the
 * cortical surface (17.0 cm) and the white matter (17.8) after the brain
 * (15.1), so the middle of the zoom stopped dead and sat at one scale for
 * three rungs. Both now live on their own pages instead.
 *
 * WHY THE STAGES ARE SEPARATE SCENES. A cortex is 0.2 m and a synaptic cleft is
 * 2e-8 m. Float32 carries about seven significant digits, so one scene holding
 * both would lose the synapse to rounding. Each stage is drawn normalised to
 * its own size and carries its true extent in metres alongside, so the zoom is
 * continuous while the arithmetic never spans more than one stage.
 *
 * SHADING FOLLOWS THE HOUSE RULE. Neurons are submerged, and submerged tissue
 * is not glossy: a real light rig, high roughness, no metalness, and emission
 * kept low enough that it cannot stand in for lighting. Pushing emission up is
 * what makes a render look flat and dead.
 *
 * ONE MOVE, NOT FOUR. Within each stage the camera makes a single push. It
 * never goes in, out and back in, which reads as pumping.
 */
import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { DRACOLoader } from "three/addons/loaders/DRACOLoader.js";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { REDUCED, makeRenderer, fitRenderer, makeLoop, fmt } from "./holo3d.js";

/* Explicit sRGB stops that climb in lightness, never interpolated through a
 * hue wheel. A blue to gold ramp walked in HSV goes the long way round through
 * green and puts a colour in the picture that neither end contains. */
const DEPTH = ["#1D358F", "#3E96F0", "#8E46C0", "#FFC24A"];

function lerpHex(a, b, t) {
  const x = new THREE.Color(a), y = new THREE.Color(b);
  return [x.r + (y.r - x.r) * t, x.g + (y.g - x.g) * t, x.b + (y.b - x.b) * t];
}
function depthRamp(t) {
  const u = Math.max(0, Math.min(1, t)) * (DEPTH.length - 1);
  const i = Math.min(DEPTH.length - 2, Math.floor(u));
  return lerpHex(DEPTH[i], DEPTH[i + 1], u - i);
}

/* The ladder now starts at 12,742 km, and the first version of this topped out
   at centimetres, so Earth was announced as "1274104174.7 cm across the view".
   Every rung above a metre was printing a number nobody can read. */
/* An emoji drawn to a canvas, so no image file has to ship for it. */
function emojiTexture(ch, px = 256) {
  const cv = document.createElement("canvas");
  cv.width = px; cv.height = px;
  const x = cv.getContext("2d");
  x.font = `${Math.round(px * 0.76)}px "Segoe UI Emoji","Apple Color Emoji",` +
           `"Noto Color Emoji",sans-serif`;
  x.textAlign = "center";
  x.textBaseline = "middle";
  x.fillText(ch, px / 2, px * 0.54);
  const t = new THREE.CanvasTexture(cv);
  t.colorSpace = THREE.SRGBColorSpace;
  return t;
}

/* Hermite ramp, so layers dissolve rather than switching off. */
function smooth(a, b, x) {
  const t = Math.max(0, Math.min(1, (x - a) / (b - a)));
  return t * t * (3 - 2 * t);
}

function humanSize(m) {
  if (m >= 1e3) return `${Math.round(m / 1e3).toLocaleString("en")} km`;
  if (m >= 1) return `${m < 10 ? m.toFixed(1) : Math.round(m)} m`;
  if (m >= 0.01) return `${(m * 100).toFixed(1)} cm`;
  if (m >= 1e-3) return `${(m * 1000).toFixed(2)} mm`;
  if (m >= 1e-6) return `${(m * 1e6).toFixed(m < 1e-5 ? 2 : 0)} µm`;
  return `${(m * 1e9).toFixed(0)} nm`;
}

/* Tissue in water, not tissue in air. The refractive step at the surface of a
 * submerged cell is tiny, so there is no highlight to speak of; the softness
 * has to come from the light rig and the roughness. */
function tissue(colour, opts = {}) {
  return new THREE.MeshStandardMaterial({
    color: new THREE.Color(colour),
    roughness: opts.roughness == null ? 0.62 : opts.roughness,
    metalness: 0.0,
    emissive: new THREE.Color(colour),
    emissiveIntensity: opts.emissive == null ? 0.05 : opts.emissive,
    transparent: true,
    opacity: opts.opacity == null ? 1 : opts.opacity,
    side: THREE.DoubleSide,
    depthWrite: opts.depthWrite !== false,
  });
}

export async function mountLadder(el) {
  const mount = el.querySelector("[data-mount]");
  const railEl = el.querySelector("[data-rail]");
  const readEl = el.querySelector("[data-read]");
  const noteEl = el.querySelector("[data-note]");
  const playEl = el.querySelector("[data-play]");
  const status = el.querySelector("[data-status]");
  if (!mount) return;

  const db = await fetch("data/ladder.json").then((r) => r.json());
  const soma = await fetch("data/somas.json").then((r) => r.json());
  /* Pia to white matter, fitted to the seven layer meshes. The neuron rungs
     are drawn in the H01 block's frame, and the block is a tilted slab: its X
     is 23.6 degrees off the cortical axis, so standing cells up along X hangs
     them crooked. Same bug as the cell gallery on the front page. */
  const depthAxis = await fetch("data/depth-axis.json")
    .then((r) => r.json()).then((d) => d.depth_axis).catch(() => null);

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(38, 16 / 9, 0.01, 400);
  const renderer = makeRenderer(mount);

  /* A real rig rather than more emission: a key, a cool fill from the other
     side, a rim behind, and enough ambient that nothing goes to pure black. */
  /* Measured off the framebuffer: at key 2.1 the cell and the cubic
     millimetre came back with 13 and 11 per cent of the frame fully
     saturated. A blown highlight on submerged tissue is exactly the painted
     plastic look the house rule is about. */
  scene.add(new THREE.AmbientLight(0xffffff, 0.50));
  const key = new THREE.DirectionalLight(0xfff3e2, 1.35);
  key.position.set(4, 5, 6);
  scene.add(key);
  const fill = new THREE.DirectionalLight(0x9fc8ff, 0.85);
  fill.position.set(-6, -1, 3);
  scene.add(fill);
  const rim = new THREE.DirectionalLight(0xffffff, 0.80);
  rim.position.set(-1, -3, -7);
  scene.add(rim);

  const loader = new GLTFLoader();
  const draco = new DRACOLoader();
  draco.setDecoderPath("vendor/three/addons/libs/draco/gltf/");
  loader.setDRACOLoader(draco);

  const load = (f) => new Promise((res, rej) =>
    loader.load(f, (g) => res(g.scene.getObjectByProperty("isMesh", true).geometry),
                undefined, rej));

  /* Every stage is normalised to two units across, so the camera never has to
     span the seven orders of magnitude the subjects do. */
  function normalise(group, target = 2.0) {
    const box = new THREE.Box3().setFromObject(group);
    const size = new THREE.Vector3(), centre = new THREE.Vector3();
    box.getSize(size); box.getCenter(centre);
    const s = target / Math.max(size.x, size.y, size.z);
    const inner = new THREE.Group();
    while (group.children.length) inner.add(group.children[0]);
    inner.position.copy(centre).multiplyScalar(-1);
    group.add(inner);
    group.scale.setScalar(s);
    return s;
  }

  const built = {};
  async function build(stage) {
    if (built[stage.id]) return built[stage.id];
    const g = new THREE.Group();

    if (stage.kind === "globe") {
      /* Day and night are two separate measurements, so they are two separate
         textures mixed by which way the surface faces the sun, rather than one
         painted composite. The terminator is therefore real geometry: the
         lights come up exactly where the ground turns away from the light.
         The gain is an exposure choice, the same kind of choice as the key
         light on the tissue rungs. It needs to be a large number because the
         face we are looking at is centred on Boston and is therefore mostly
         North Atlantic, and ocean reflectance really is that dark: measured
         off the framebuffer the planet came back at mean luminance 31 out of
         255, which is a black disc with a rumour of blue in it. */
      const tex = (f) => new Promise((res) => {
        const t = new THREE.TextureLoader().load(f, () => res(t));
        t.colorSpace = THREE.SRGBColorSpace;
      });
      const [day, night] = await Promise.all([tex(stage.day), tex(stage.night)]);
      const mat = new THREE.ShaderMaterial({
        uniforms: { day: { value: day }, night: { value: night },
                    sun: { value: new THREE.Vector3(0.72, 0.34, 0.60) },
                    opacity: { value: 1 } },
        /* Transparent AND writing depth is the combination that flickers.
           Every rung sits at the same origin, so two crossfading rungs fight
           over the depth buffer and which one wins changes with the sort,
           frame to frame. Order is already decided explicitly by renderOrder;
           the depth buffer must not get a second vote. */
        transparent: true, depthWrite: false,
        vertexShader: `varying vec2 vUv; varying vec3 vN;
          void main(){ vUv = uv; vN = normalize(normalMatrix * normal);
            gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }`,
        fragmentShader: `uniform sampler2D day, night; uniform vec3 sun;
          uniform float opacity; varying vec2 vUv; varying vec3 vN;
          void main(){
            float l = dot(normalize(vN), normalize(sun));
            float t = smoothstep(-0.10, 0.24, l);
            vec3 d = texture2D(day, vUv).rgb * (0.42 + 1.05 * max(l, 0.0));
            vec3 n = texture2D(night, vUv).rgb * 1.45;
            gl_FragColor = vec4(mix(n, d, t), opacity);
            /* A texture tagged sRGB is decoded to linear when it is sampled,
               but a raw ShaderMaterial never gets the encode back on the way
               out: three.js only applies it through these chunks. Without
               them every hand-written shader on the page was being published
               with a gamma still on it, which is why the planet measured 31
               out of 255 and no amount of gain fixed it. Chasing that with
               brightness rather than finding it would have left the colours
               wrong as well as the level. */
            #include <tonemapping_fragment>
            #include <colorspace_fragment> }`,
      });
      const sph = new THREE.Mesh(new THREE.SphereGeometry(1, 96, 64), mat);
      /* Turn Boston to the front. An equirectangular map on a three.js sphere
         puts longitude 0 at -Z, so the meridian we want faces the camera at
         -lon - 90 degrees. */
      sph.rotation.y = THREE.MathUtils.degToRad(-stage.lon - 90);
      g.add(sph);
    } else if (stage.kind === "plate") {
      /* A photograph already contains its own light. Running it through the
         tissue rig would tint it with the key and the fill and make a
         measurement look like a rendering, so these are unlit. */
      const t = await new Promise((res) => {
        const x = new THREE.TextureLoader().load(stage.image, () => res(x));
        x.colorSpace = THREE.SRGBColorSpace;
        x.anisotropy = 8;
      });
      /* The histology plates are photographs of a slide, and most of a slide is
         empty paraffin, which is very nearly white. Drawn as-is they came back
         with eight to fourteen per cent of the frame fully saturated: a white
         slab on a black page, with the tissue a small dark island in it. So the
         empty resin is dropped to transparent and the tissue floats on the
         page's own ground. This is not a cosmetic dodge; the resin is literally
         nothing, and drawing nothing as the brightest thing on screen is the
         misleading version. The satellite frames do NOT get this, because up
         there the bright pixels are clouds and clouds are the weather. */
      const cut = !!stage.cutout;
      g.add(new THREE.Mesh(new THREE.PlaneGeometry(2, 2), cut
        ? new THREE.ShaderMaterial({
            uniforms: { map: { value: t }, opacity: { value: 1 } },
            transparent: true, side: THREE.DoubleSide, depthWrite: false,
            vertexShader: `varying vec2 vUv;
              void main(){ vUv = uv;
                gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }`,
            fragmentShader: `uniform sampler2D map; uniform float opacity;
              varying vec2 vUv;
              void main(){ vec3 c = texture2D(map, vUv).rgb;
                /* The alpha threshold is judged on the sRGB value a reader
                   would see, not on the linear one, so undo the decode for
                   the test only and leave the colour itself alone. */
                vec3 srgb = pow(c, vec3(0.4545));
                float lum = dot(srgb, vec3(0.299, 0.587, 0.114));
                gl_FragColor = vec4(c, smoothstep(0.97, 0.80, lum) * opacity);
                #include <tonemapping_fragment>
                #include <colorspace_fragment> }`,
          })
        : new THREE.MeshBasicMaterial({ map: t, transparent: true,
                                        side: THREE.DoubleSide,
                                        depthWrite: false })));
    } else if (stage.kind === "body") {
      /* Three layers from one scan in one frame, so the brain does not have to
         be placed inside the head by eye. The reveal is driven by position on
         the ladder rather than by a timer: as the scale descends through this
         rung the skin goes first, then the skeleton, and the camera flies into
         the head, so by the time the next rung takes over the brain is already
         where the next rung's brain will be. */
      for (const L of stage.layers) {
        const geo = await load(L.file);
        geo.computeVertexNormals();
        const solid = L.role === "brain";
        const m = new THREE.Mesh(geo, tissue(L.colour, {
          roughness: L.role === "skeleton" ? 0.72 : 0.66,
          emissive: solid ? 0.07 : 0.04,
          depthWrite: true,
        }));
        m.userData.role = L.role;
        g.add(m);
      }
      /* A fig leaf, until a clothed model arrives. Placed from the atlas's own
         genital-system mesh rather than by eye, so it cannot drift off the
         thing it is covering when the geometry or the decimation changes, and
         it goes when the skin does, because after that there is nothing to
         cover. depthTest off so it stays in front of the body it is on. */
      if (stage.figLeaf) {
        const sp = new THREE.Sprite(new THREE.SpriteMaterial({
          map: emojiTexture("😉"), transparent: true,
          depthTest: false, depthWrite: false,
        }));
        sp.position.fromArray(stage.figLeaf.centre_m);
        const w = stage.figLeaf.size_m * 4.2;   // the structure is 34 mm; a
        // sticker exactly the size of what it covers does not cover it
        sp.scale.set(w, w, w);
        sp.userData.role = "figleaf";
        g.add(sp);
      }
      g.rotation.x = -Math.PI / 2;      // the atlas is Z-up, three.js is Y-up
    } else if (stage.kind === "wholebrain") {
      for (const m of stage.meshes) {
        const geo = await load(m.file);
        geo.computeVertexNormals();
        /* The shell is a glass case around the structures rather than a solid
           object, so it must not write depth or it culls its own contents. */
        const solid = m.role === "interior";
        const mat = tissue(m.colour, {
          roughness: solid ? 0.6 : 0.75, opacity: m.opacity,
          depthWrite: solid, emissive: solid ? 0.06 : 0.03,
        });
        /* The shell is glass and must be FrontSide. DoubleSide draws the far
           wall of the skull as well as the near one, so every place the
           surface folds gets two translucent layers instead of one and the
           brain fills with bright patches that look like structures and are
           not. tracts.js already says this in as many words about its own
           glass brain; this rung never got the same treatment. */
        if (!solid) mat.side = THREE.FrontSide;
        g.add(new THREE.Mesh(geo, mat));
      }
    } else if (stage.kind === "surface") {
      for (const m of stage.meshes) {
        const geo = await load(m.file);
        geo.computeVertexNormals();
        g.add(new THREE.Mesh(geo, tissue(m.colour, { roughness: 0.68 })));
      }
    } else if (stage.kind === "tracts") {
      const meta = await fetch("data/tracts.json").then((r) => r.json());
      const buf = await fetch(meta.bin).then((r) => r.arrayBuffer());
      const K = meta.bundles[0].points_per_line;
      const GROUP = { Association: "#3E96F0", Projection: "#FFB24D",
                      Commissural: "#B884FF", Cerebellum: "#3FE3B0",
                      "Cranial nerve": "#FF5C7A" };
      const pos = [], col = [];
      meta.bundles.forEach((b) => {
        const c = new THREE.Color(GROUP[b.group] || "#8b94a3");
        const q = new Int16Array(buf, b.offset, b.lines * K * 3);
        for (let l = 0; l < b.lines; l += 2) {          // half of them is plenty
          for (let k = 0; k < K - 1; k++) {
            const a = l * K * 3 + k * 3, d = a + 3;
            pos.push(q[a] / meta.scale, q[a + 1] / meta.scale, q[a + 2] / meta.scale,
                     q[d] / meta.scale, q[d + 1] / meta.scale, q[d + 2] / meta.scale);
            col.push(c.r, c.g, c.b, c.r, c.g, c.b);
          }
        }
      });
      const geo = new THREE.BufferGeometry();
      geo.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
      geo.setAttribute("color", new THREE.Float32BufferAttribute(col, 3));
      g.add(new THREE.LineSegments(geo, new THREE.LineBasicMaterial({
        /* Measured: at 0.55 the tract rung came back 10.6 per cent fully
           saturated, which is the whole white matter reading as one white
           mass. Additive blending over half a million segments needs a very
           per-segment alpha. Lowering it did not solve this: 0.55 gave 10.6
           per cent of the frame fully saturated, 0.22 gave 8.2 and 0.09 still
           gave 5.4, because additive blending over half a million overlapping
           segments sums to white whatever the alpha is. Normal blending
           cannot, so the bundles read as cable rather than as one glowing
           mass. */
        vertexColors: true, transparent: true, opacity: 0.34,
        depthWrite: false, blending: THREE.NormalBlending,
      })));
    } else if (stage.kind === "block") {
      const buf = await fetch(soma.bin).then((r) => r.arrayBuffer());
      const n = soma.count;
      const off = {};
      soma.layout.forEach((f) => { off[f.field] = f.offset; });
      const xyz = new Float32Array(buf, off.xyz, n * 3);
      const depth = new Float32Array(buf, off.depth, n);
      const lo = soma.bounds_um[0], hi = soma.bounds_um[1];
      const mid = [0, 1, 2].map((i) => (lo[i] + hi[i]) / 2);
      const P = new Float32Array(n * 3), C = new Float32Array(n * 3);
      const dmax = soma.cortex_depth_um;
      for (let i = 0; i < n; i++) {
        P[i * 3] = xyz[i * 3 + 1] - mid[1];
        P[i * 3 + 1] = xyz[i * 3] - mid[0];
        P[i * 3 + 2] = xyz[i * 3 + 2] - mid[2];
        const c = depthRamp(depth[i] / dmax);
        C[i * 3] = c[0]; C[i * 3 + 1] = c[1]; C[i * 3 + 2] = c[2];
      }
      const geo = new THREE.BufferGeometry();
      geo.setAttribute("position", new THREE.BufferAttribute(P, 3));
      geo.setAttribute("color", new THREE.BufferAttribute(C, 3));
      g.add(new THREE.Points(geo, new THREE.PointsMaterial({
        /* 49,379 additively blended points at six pixels cover the wafer
           several times over and the middle goes solid white. */
        size: 3.2, sizeAttenuation: false, vertexColors: true,
        transparent: true, opacity: 0.13, depthWrite: false,
        blending: THREE.AdditiveBlending,
      })));
    } else if (stage.kind === "cell") {
      const geo = await load(stage.mesh);
      geo.computeVertexNormals();
      /* A 2.1 mm neuron drawn whole is mostly empty space with very thin
         branches: measured, it lit 0.2 per cent of the frame against 14 for
         the rungs either side of it. The rig is not the problem, the subject
         is thin, so this one carries a little more emission and a lighter
         base than the solid surfaces do. */
      const m = new THREE.Mesh(geo, tissue("#8FC4FF", {
        roughness: 0.55, emissive: 0.30 }));
      if (depthAxis) {
        m.quaternion.setFromUnitVectors(
          new THREE.Vector3().fromArray(depthAxis).normalize(),
          new THREE.Vector3(0, -1, 0));    // pia up, white matter down
      } else {
        m.rotation.z = Math.PI / 2;
      }
      g.add(m);
    } else if (stage.kind === "synapse") {
      for (const m of stage.meshes) {
        const geo = await load(m.file);
        geo.computeVertexNormals();
        g.add(new THREE.Mesh(geo, tissue(m.colour, { roughness: 0.55 })));
      }
    }

    normalise(g);

    if (stage.kind === "body") {
      /* Where is the brain inside the normalised body, and how much would the
         camera have to close in for it to fill the frame the way the next rung
         does? Both measured off the built geometry rather than typed, because
         a hand-typed offset would drift the moment the atlas or the decimation
         changed. */
      let brainMesh = null;
      g.traverse((o) => { if (o.userData.role === "brain") brainMesh = o; });
      /* Box3.setFromObject reads matrixWorld, and this group is not in the
         scene yet, so without this the box comes back in the mesh's own
         untransformed coordinates: the head pointed down +Z instead of +Y and
         the zoom factor came out 11.06 instead of 9.56. Both numbers looked
         entirely reasonable, which is the problem with them. */
      g.updateMatrixWorld(true);
      const box = new THREE.Box3().setFromObject(brainMesh);
      const c = new THREE.Vector3(), s = new THREE.Vector3();
      box.getCenter(c); box.getSize(s);
      /* Store the world position at build scale. Uniform scale commutes with
         the rotation, so at scale factor Z the brain centre sits at
         brainWorld * Z, and the pan that keeps it centred is just minus that. */
      g.userData.brainWorld = c.clone();
      g.userData.brainZoom = 2.0 / Math.max(s.x, s.y, s.z);
      console.info("[ladder] body: brain at", c.toArray().map((v) => +v.toFixed(3)),
                   "needs", g.userData.brainZoom.toFixed(2), "x to fill the frame");
    }

    g.visible = false;
    /* Draw order matters here. The rung being zoomed INTO has to be painted
       before the rung being left, so the outgoing one dissolves to reveal it
       rather than being hidden behind it. Deeper rungs therefore get a lower
       render order and go down first. */
    const idx = db.stages.indexOf(stage);
    /* The fig leaf is the exception and has to be last of all. depthTest is
       already off on it, but that only stops it being REJECTED by the depth
       buffer; it does not decide when it is painted. Sharing a render order
       with the body meant three.js sorted them back to front by distance, and
       the anatomy protrudes in front of the sprite's centroid, so it was
       painted after the sprite and straight over the top of it. */
    g.traverse((o) => {
      o.renderOrder = o.userData.role === "figleaf" ? 9999 : -idx;
    });
    scene.add(g);
    built[stage.id] = g;
    return g;
  }

  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.09;
  controls.enablePan = false;
  controls.enableZoom = false;          // the zoom IS the page; do not fight it
  controls.minDistance = 1;
  controls.maxDistance = 20;
  renderer.domElement.style.cursor = "grab";

  /* The parameter is position along the ladder, not log of the size, because
     the steps run from 1.7x to 701x and a metric parameter would spend most of
     the run inside the cell-to-synapse gap and flick through everything else.
     The readout still prints the real size, interpolated in log space between
     neighbours, so the number on screen is always the true width. */
  const N = db.stages.length;
  const LOGF = db.stages.map((s) => Math.log10(s.fov_m));
  /* How fast each rung grows as the ladder passes it. This was a flat 4.6x
     everywhere, which meant the picture zoomed the same amount whether the
     number changed by 1.7 times or by 244, and that mismatch is what reads as
     the scale being wrong. Now it follows the real ratio, clamped: below two
     the move is too small to register as a zoom at all, and above nine it is a
     lurch. Only the two steps in the sky are big enough to hit the ceiling. */
  const RATE = db.stages.map((s, i) => (i >= N - 1) ? 4.0
    : Math.max(2.0, Math.min(9.0, s.fov_m / db.stages[i + 1].fov_m)));
  const Z = db.stages.map((_, i) => i);          // rung positions
  const zTop = 0, zBot = N - 1;
  let z = zTop, playing = !REDUCED, dir = 1;

  function fovAt(u) {
    const i = Math.max(0, Math.min(N - 2, Math.floor(u)));
    const f = Math.max(0, Math.min(1, u - i));
    /* Exactly on a rung, print the stored number rather than the round trip
       through log space: 12,742,000 m came back as 12,741 km, and being one
       kilometre out on the diameter of the Earth is the kind of thing that
       reads as carelessness about every other figure on the page. */
    if (f === 0) return db.stages[i].fov_m;
    if (f === 1) return db.stages[i + 1].fov_m;
    return Math.pow(10, LOGF[i] + (LOGF[i + 1] - LOGF[i]) * f);
  }

  /* How present is a stage at the current scale? One at its own rung, fading
     out over roughly half a decade either side, so consecutive rungs dissolve
     into one another instead of cutting. */
  /* Asymmetric on purpose. A rung is growing the whole time it is on screen,
     so if it faded out at the same rate it fades in, it spends the end of its
     life covering the entire frame at low opacity and hiding the rung arriving
     behind it, then disappears all at once. Measured: at 0.7 past its own rung
     the brain still filled 100 per cent of the frame, and one step later the
     frame was 11 per cent full. That is a cut, not a zoom.

     So: come in slowly from far away, leave quickly once oversize. */
  /* Asymmetric, and both halves were tuned against the framebuffer rather than
     by eye. A rung grows the whole time it is on screen, so a symmetric fade
     leaves it covering the entire frame at low opacity, hiding whatever is
     arriving behind it, and then dropping out all at once: measured, the frame
     went from 100 per cent covered to 11 in one step, which is a cut.

     Fading it out faster fixed that and broke something else. Halfway between
     two rungs the outgoing one had gone and the incoming one was still small,
     so mean frame brightness fell from 41 to 3.6 out of 255. Every transition
     dipped through black.

     So the incoming rung comes up early and holds, while it is still small and
     far away, and the outgoing one dissolves over it. Nothing is asked to
     carry the frame on its own. */
  function presence(i) {
    const d = z - i;
    if (d < 0) return 1 - smooth(0, i === 0 ? 1.9 : 1.60, -d);
    return 1 - smooth(0, i === N - 1 ? 1.9 : 0.85, d);
  }

  function apply() {
    let best = 0, bestP = -1;
    db.stages.forEach((s, i) => {
      const g = built[s.id];
      const pr = presence(i);
      if (pr > bestP) { bestP = pr; best = i; }
      if (!g) return;
      g.visible = pr > 0.01;
      /* The reveal. Within the person rung, `u` runs 0 to 1 as the scale
         descends past it: the skin goes first, the skeleton follows, and the
         brain is what is left standing. Driven by position on the ladder, not
         by a clock, so scrubbing backwards puts the body back on. */
      const u = s.kind === "body" ? Math.max(0, Math.min(1, z - i)) : 0;
      const skin = 1 - smooth(0.02, 0.42, u);
      const peel = { skin,
                     skeleton: 1 - smooth(0.40, 0.80, u),
                     brain: 1,
                     /* Goes with the skin. Once that is off there is a
                        skeleton on screen and nothing left to cover. */
                     figleaf: skin };

      g.traverse((o) => {
        if (!o.material) return;
        const layer = o.userData.role ? peel[o.userData.role] : 1;
        const mats = Array.isArray(o.material) ? o.material : [o.material];
        mats.forEach((mm) => {
          mm.visible = layer > 0.004;
          mm.transparent = true;
          const base = mm.userData.base == null
            ? (mm.userData.base = (mm.uniforms ? mm.uniforms.opacity.value
                                               : mm.opacity))
            : mm.userData.base;
          /* The globe is a ShaderMaterial, so its opacity is a uniform and
             setting material.opacity on it does nothing at all: it would fade
             every other rung and stay solid itself. */
          if (mm.uniforms && mm.uniforms.opacity) mm.uniforms.opacity.value = base * pr;
          else mm.opacity = base * pr * layer;
        });
      });
      /* THE ZOOM. Each rung grows steadily as the ladder descends past it, so
         the thing you are looking at swells and you fall through it into the
         next one. Before its own rung it is small and growing; after it, it is
         oversize and on its way out of frame. That is what makes this read as
         one continuous push rather than a slideshow that cross-dissolves in
         place, which is what it was.

         The growth rate is a fixed factor per rung, NOT the true ratio between
         neighbours. Those ratios run from 1.7x to 701x, and driving the visual
         zoom with them would make the cell-to-synapse step a violent lurch and
         the brain-to-cortex step barely move. The honest number is already on
         screen in the readout, which is the channel that has to carry it; the
         transition only has to be legible. */
      const d = z - i;
      const grow = Math.pow(RATE[i], d);
      if (s.kind === "body") {
        /* The person rung does not get the gentle push the others do, because
           it has somewhere specific to go. It closes in on the head by exactly
           the factor that makes the brain fill the frame the way the next rung
           does, so when the crossfade hands over, the atlas brain and the HD
           brain are the same size in the same place and the join does not
           jump. The pan is minus the brain's position times the current scale,
           which keeps it dead centre the whole way in. */
        /* On the way IN it grows like every other rung. On the way THROUGH it
           does something specific instead: it closes on the head by exactly
           the factor that makes the brain fill the frame the way the next rung
           does, so when the handover comes the atlas brain and the HD brain
           are the same size in the same place and the join does not jump. The
           pan is minus the brain's position times the current scale, which
           holds it dead centre the whole way in. */
        /* THE PAN HAS TO LEAD THE ZOOM, not travel with it. Both ran on the
           same ramp before, and the arithmetic of that is unforgiving: the
           head sits 0.89 units above the body's centre, and if the pan is only
           half done when the scale is already up five times, the head is
           0.89 x 5.26 x 0.5 = 2.3 units above frame centre, in a frame two
           units tall. So the zoom went into the belly, the head climbed out of
           the top of the picture, and it only came back at the very end.

           The pan is therefore finished by 45 per cent of the way through the
           rung while the zoom keeps going to the end: settle on the head
           first, then close on it. */
        const e = smooth(0, 1, u);
        const f = smooth(0, 0.45, u);
        const Zf = (1 + (g.userData.brainZoom - 1) * e) * Math.min(1, grow);
        g.scale.setScalar(g.userData.baseScale * Zf);
        g.position.copy(g.userData.brainWorld).multiplyScalar(-f * Zf);
      } else {
        g.scale.setScalar(g.userData.baseScale * grow);
        g.position.set(0, 0, 0);
      }
    });

    const s = db.stages[best];
    const fov = fovAt(z);
    if (readEl) {
      readEl.innerHTML =
        `<b>${humanSize(fov)}</b><u>across the view</u>`;
    }
    if (noteEl) {
      noteEl.innerHTML = `<h3>${s.name}</h3><p>${s.note}</p>` +
        `<p class="src">${s.source}</p>`;
    }
    if (railEl) {
      const f = (z - zTop) / (zBot - zTop);
      railEl.style.setProperty("--at", `${(f * 100).toFixed(2)}%`);
      railEl.querySelectorAll("[data-i]").forEach((b) =>
        b.setAttribute("aria-current", String(+b.dataset.i === best)));
    }
  }

  const loop = makeLoop(el, (dt) => {
    if (playing) {
      z += dir * dt * 0.26;                 // rungs per second
      if (z >= zBot) { z = zBot; dir = -1; }
      if (z <= zTop) { z = zTop; dir = 1; }
      apply();
    }
    controls.update();
    renderer.render(scene, camera);
  });
  fitRenderer(renderer, camera, mount);
  new ResizeObserver(() => { if (fitRenderer(renderer, camera, mount)) loop.once(); })
    .observe(mount);

  if (status) status.textContent = "Loading sixteen scales";
  for (const s of db.stages) {
    // eslint-disable-next-line no-await-in-loop
    const g = await build(s);
    g.userData.baseScale = g.scale.x;
  }
  if (status) status.textContent = "";

  /* Solved rather than guessed: each stage is normalised to two units, the
     field of view is 38 degrees, so this puts a rung at about four fifths of
     the frame height at rest, and the push above keeps it under nine tenths. */
  camera.position.set(0, 0, 3.7);
  controls.target.set(0, 0, 0);

  if (railEl) {
    railEl.innerHTML = `<i></i>` + db.stages.map((s, i) =>
      `<button type="button" data-i="${i}" style="top:${
        (i / (N - 1) * 100).toFixed(2)}%">` +
      `<s></s><span>${s.name}</span><em>${humanSize(s.fov_m)}</em></button>`).join("");
    railEl.addEventListener("click", (e) => {
      const b = e.target.closest("[data-i]");
      if (!b) return;
      playing = false;
      if (playEl) playEl.textContent = "Play";
      z = +b.dataset.i;
      apply(); loop.once();
    });
  }
  if (playEl) {
    playEl.textContent = playing ? "Pause" : "Play";
    playEl.addEventListener("click", () => {
      playing = !playing;
      playEl.textContent = playing ? "Pause" : "Play";
      loop.once();
    });
  }
  /* The wheel drives the scale rather than the camera, because the scale is
     what this page is about. */
  mount.addEventListener("wheel", (e) => {
    e.preventDefault();
    playing = false;
    if (playEl) playEl.textContent = "Play";
    z = Math.max(zTop, Math.min(zBot, z + Math.sign(e.deltaY) * 0.05));
    apply(); loop.once();
  }, { passive: false });

  apply();
  loop.run();
  return { loop, db, apply, setZ: (v) => { z = v; apply(); loop.once(); },
           getZ: () => z, stages: built, Z, fovAt, N };
}
