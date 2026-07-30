/* Shared plumbing for the three interactive panels on this page.
 *
 * Every one of them is the same shape: a canvas that must not start until the
 * reader can see it, must stop the moment they scroll away, and must give the
 * frame back when the tab goes into the background. Three copies of that logic
 * is three chances to leak a render loop, so it lives here once.
 *
 * The rule this file exists to enforce: a WebGL context that nobody is looking
 * at renders nothing. Three of them on one article would otherwise sit there
 * spinning the GPU for the whole time the page is open.
 */
import * as THREE from "three";

export const REDUCED =
  window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/* A renderer sized to its container, on a transparent clear colour so the
 * page's own black shows through and the panel reads as a window rather than
 * a pasted-in box. */
export function makeRenderer(mount) {
  const r = new THREE.WebGLRenderer({
    antialias: true, alpha: true, powerPreference: "low-power",
  });
  r.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  r.setClearColor(0x000000, 0);
  r.outputColorSpace = THREE.SRGBColorSpace;
  r.domElement.style.display = "block";
  r.domElement.style.width = "100%";
  r.domElement.style.height = "100%";
  r.domElement.style.touchAction = "none";
  mount.appendChild(r.domElement);
  return r;
}

export function fitRenderer(renderer, camera, mount) {
  const w = mount.clientWidth, h = mount.clientHeight;
  if (!w || !h) return false;
  renderer.setSize(w, h, false);
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
  return true;
}

/* Runs `frame(dt, t)` only while the element is on screen, the tab is visible
 * and the panel has actually been started. Returns a handle with stop().
 *
 * The deliberate part: nothing here starts on its own. The caller decides when
 * a panel is worth a WebGL context, which is what keeps a page carrying three
 * of them from opening three at once on load. */
export function makeLoop(el, frame) {
  let raf = 0, last = 0, t = 0, onScreen = false, running = false;

  function step(now) {
    const dt = last ? Math.min(0.05, (now - last) / 1000) : 0;
    last = now; t += dt;
    frame(dt, t);
    raf = requestAnimationFrame(step);
  }
  function start() {
    if (raf || !onScreen || document.hidden || !running) return;
    last = 0;
    raf = requestAnimationFrame(step);
  }
  function halt() { cancelAnimationFrame(raf); raf = 0; }

  document.addEventListener("visibilitychange", function () {
    document.hidden ? halt() : start();
  });
  if (window.IntersectionObserver) {
    new IntersectionObserver(function (es) {
      onScreen = es[0].isIntersecting;
      onScreen ? start() : halt();
    }, { threshold: 0.05 }).observe(el);
  } else {
    onScreen = true;
  }

  return {
    run: function () { running = true; onScreen = onScreen || !window.IntersectionObserver; start(); },
    /* one frame, on demand, for the case where the loop is legitimately
       stopped but the scene changed and the canvas would otherwise go stale */
    once: function () { frame(0, t); },
    /* Advance by a given dt without a real frame. This is how the timed
       panels get checked: a headless or backgrounded tab composites nothing,
       so requestAnimationFrame never fires and an animation cannot be
       observed running. Driving the same frame function by hand tests the
       real state machine rather than a copy of it. */
    step: function (dt) { t += dt; frame(dt, t); },
    stop: function () { running = false; halt(); },
  };
}

/* The panels are heavy: several megabytes of real mesh each. None of them
 * fetches anything until the reader is near it. The button is not a fallback
 * for a broken observer, it is the affordance for a reader who wants it now,
 * and it is also the only way in when IntersectionObserver is missing. */
export function whenNear(el, load) {
  let done = false;
  function go() {
    if (done) return;
    done = true;
    load();
  }
  if (window.IntersectionObserver) {
    const io = new IntersectionObserver(function (es) {
      if (es[0].isIntersecting) { io.disconnect(); go(); }
    }, { rootMargin: "300px" });
    io.observe(el);
  } else {
    go();
  }
  return go;
}

/* Studio lighting. Two keys and a rim, which is what stops a single coloured
 * emissive surface from reading as a flat silhouette. */
export function studioLights(scene, tint) {
  scene.add(new THREE.AmbientLight(0xffffff, 0.5));
  const key = new THREE.DirectionalLight(0xffffff, 1.0);
  key.position.set(2, 4, 5);
  scene.add(key);
  const fill = new THREE.DirectionalLight(new THREE.Color(tint), 0.4);
  fill.position.set(-3, 1, -2);
  scene.add(fill);
  const rim = new THREE.DirectionalLight(0xffffff, 0.45);
  rim.position.set(0, -2, -5);
  scene.add(rim);
}

/* A solid surface with a bright wireframe lifted just off it. The wireframe is
 * additive with depthWrite off and the polygon offset keeps it from z fighting
 * the surface it sits on. Carried across from Inner Cosmos, where it is what
 * makes a scanned surface read as measured rather than modelled. */
export function shellMaterials(obj, opts) {
  const solid = new THREE.MeshStandardMaterial({
    color: new THREE.Color(opts.color),
    emissive: new THREE.Color(opts.emissive),
    emissiveIntensity: opts.emissiveIntensity == null ? 0.35 : opts.emissiveIntensity,
    roughness: 0.7, metalness: 0.0,
    transparent: true, opacity: opts.opacity == null ? 1 : opts.opacity,
    /* DoubleSide on a translucent shell draws the far wall as well as the near
       one, and with an additive wireframe on top the two sum and the whole
       thing goes white. A glass shell wants FrontSide. */
    side: opts.side === "front" ? THREE.FrontSide : THREE.DoubleSide,
    /* A shell with something inside it worth seeing has to stop writing depth,
       or it culls its own contents. */
    depthWrite: opts.depthWrite == null ? true : opts.depthWrite,
  });
  obj.material = solid;
  const wire = new THREE.MeshBasicMaterial({
    color: new THREE.Color(opts.wire),
    wireframe: true, transparent: true,
    opacity: opts.wireOpacity == null ? 0.16 : opts.wireOpacity,
    blending: THREE.AdditiveBlending,
    polygonOffset: true, polygonOffsetFactor: -1, polygonOffsetUnits: -1,
    depthWrite: false,
  });
  obj.add(new THREE.Mesh(obj.geometry, wire));
  return { solid: solid, wire: wire };
}

export function disposeTree(root) {
  root.traverse(function (o) {
    if (!o.isMesh) return;
    if (o.geometry) o.geometry.dispose();
    const m = o.material;
    if (Array.isArray(m)) m.forEach(function (x) { x.dispose(); });
    else if (m) m.dispose();
  });
}

export function fmt(n, dp) {
  return n.toLocaleString("en-US", {
    minimumFractionDigits: dp || 0, maximumFractionDigits: dp || 0,
  });
}
