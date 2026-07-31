"""Rebuild per-vertex data in the compressed mesh's own vertex order.

THE BUG THIS EXISTS FOR. Draco does not preserve vertex order. Measured in
three.js with the same loader the pages use, compressing a 60,002 vertex
surface returns 60,002 vertices whose mean displacement from the originals is
144 units and whose maximum is 281. Not one vertex lands within quantisation
distance of where it started. Every array this repository ships that is indexed
by vertex number was therefore painted onto the wrong vertices.

It was not obvious by eye, which is what makes it dangerous. Draco's reordering
retains some locality, so a scrambled retinotopic map still looks broadly
organised. Measured in the browser, the shipped angle map scored a smoothness
ratio of 0.54 against 0.13 in the source data: four times worse, and still not
obviously wrong to look at.

TWO WRONG TURNS WORTH RECORDING, because both produced confident nonsense.
  1. trimesh cannot read Draco compressed glTF. It returns the right vertex
     COUNT with every position at the origin. Any comparison against it gives a
     constant distance for every vertex, which looks like a scramble and is
     actually an empty array. Both of the first two investigations here were
     measuring that.
  2. Trying to recover the order by re-deriving the uncompressed mesh fails,
     because quadric decimation is not reproducible run to run.

WHAT WORKS. `gltf-transform cp` decodes Draco back to plain glTF, which trimesh
can read. Matching those decoded positions against the originals recovers the
permutation exactly: the worst match is 0.015 against a vertex spacing of 0.449.
The value arrays are then permuted into the compressed order.

Run after scripts/draco.sh. Safe to re-run: it always rebuilds from source.
"""

import json
import os
import subprocess
import tempfile

import numpy as np
import trimesh
from scipy.spatial import cKDTree

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def p(*a):
    return os.path.join(ROOT, *a)


def decoded_vertices(glb):
    """Vertices of a Draco glTF, in the order the browser will see them."""
    tmp = os.path.join(tempfile.mkdtemp(), "decoded.glb")
    subprocess.run(["npx", "--yes", "@gltf-transform/cli@latest", "cp", glb, tmp],
                   check=True, shell=True, capture_output=True)
    m = trimesh.load(tmp, force="mesh", process=False)
    v = np.asarray(m.vertices, np.float64)
    if v.size == 0 or not np.isfinite(v).all() or np.allclose(v, 0):
        raise SystemExit(f"{glb}: decode produced nothing usable")
    return v


def permutation(original, glb, label):
    """For each compressed vertex, which original vertex is it?"""
    cv = decoded_vertices(glb)
    ref = np.asarray(original, np.float64)
    d, idx = cKDTree(ref).query(cv, k=1)
    spacing = float(np.median(cKDTree(ref).query(ref, k=2)[0][:, 1]))
    print(f"    {label}: {len(cv):,} vertices, worst match {d.max():.4f} "
          f"against spacing {spacing:.4f}, "
          f"{len(np.unique(idx)):,} of {len(ref):,} originals hit")
    if d.max() > spacing * 0.5:
        raise SystemExit(f"{label}: match is not safe ({d.max()} vs {spacing})")
    return idx, len(cv)


# --------------------------------------------------------------- retino ----
def fix_retinotopy():
    import nibabel as nib
    meta = json.load(open(p("data", "retinotopy.json"), encoding="utf-8"))
    out, layout = bytearray(), []
    for h in ("lh", "rh"):
        v, _ = nib.freesurfer.read_geometry(p(".cache", "retino", f"{h}.inflated"))
        maps = {k: np.asarray(nib.load(p(".cache", "retino", f"{h}.{k}.mgz"))
                              .get_fdata()).squeeze()
                for k in ("angle", "eccen", "vexpl")}
        # The compressed mesh is decimated, so its vertices do not sit exactly
        # on original ones; match into the full resolution surface instead,
        # which is the same nearest neighbour resampling the build already did.
        cv = decoded_vertices(p("meshes", "retino", f"{h}.glb"))
        d, idx = cKDTree(np.asarray(v, np.float64)).query(cv, k=1)
        print(f"    {h}: {len(cv):,} vertices resampled from {len(v):,}, "
              f"median move {np.median(d):.3f} mm, worst {d.max():.3f}")
        assert np.median(d) < 1.5, f"{h}: resampling moved too far"
        n = len(cv)
        a16 = np.round((maps["angle"][idx] + np.pi) / (2 * np.pi) * 65535
                       ).clip(0, 65535).astype("<u2")
        e16 = np.round(np.clip(maps["eccen"][idx], 0, 40) / 40 * 65535).astype("<u2")
        v8 = np.round(np.clip(maps["vexpl"][idx], 0, 1) * 255).astype(np.uint8)
        for name, arr in (("angle", a16), ("eccen", e16), ("vexpl", v8)):
            layout.append({"hemi": h, "field": name, "offset": len(out),
                           "count": int(n),
                           "dtype": "uint16" if arr.dtype == np.uint16 else "uint8"})
            out += arr.tobytes()
        meta["meshes"][h]["vertices"] = int(n)
    open(p("data", "retinotopy.bin"), "wb").write(bytes(out))
    meta["layout"] = layout
    meta["built_from_compressed_mesh"] = True
    meta["resampling"] = (
        "Values are sampled from the full resolution surface at each COMPRESSED "
        "vertex's position, after Draco. Draco reorders vertices, so anything "
        "indexed by vertex number before compression is painted on the wrong "
        "place; deriving the values from the compressed mesh makes the order "
        "irrelevant.")
    json.dump(meta, open(p("data", "retinotopy.json"), "w", encoding="utf-8"),
              indent=1, ensure_ascii=False)
    print(f"  retinotopy.bin rewritten, {len(out)/1e6:.2f} MB")


# ---------------------------------------------------------------- hires ----
def fix_hires():
    import nibabel as nib
    import mne
    mne.set_log_level("WARNING")
    meta = json.load(open(p("data", "hires.json"), encoding="utf-8"))
    fsdir = os.path.join(os.path.expanduser("~"), "mne_data",
                         "MNE-fsaverage-data", "fsaverage")
    src = mne.read_source_spaces(
        os.path.join(fsdir, "bem", "fsaverage-ico-5-src.fif"), verbose=False)
    out, layout, off = bytearray(), [], 0
    for (h, s) in zip(("lh", "rh"), src):
        sphere, _ = nib.freesurfer.read_geometry(
            os.path.join(fsdir, "surf", f"{h}.sphere"))
        used = s["vertno"]
        # Each surface is compressed separately and lands in its own order, so
        # each gets its own index array rather than being assumed to agree.
        for kind in ("inflated", "white"):
            v, _ = nib.freesurfer.read_geometry(
                os.path.join(fsdir, "surf", f"{h}.{kind}"))
            idx, n = permutation(v, p("meshes", "hires", f"{h}-{kind}.glb"),
                                 f"{h}-{kind}")
            near = cKDTree(sphere[used]).query(sphere[idx], k=1)[1]
            layout.append({"hemi": h, "kind": kind, "offset": len(out),
                           "count": int(n), "source_offset": off,
                           "sources": int(len(used))})
            out += near.astype("<u2").tobytes()
            meta["meshes"][f"{h}-{kind}"]["vertices"] = int(n)
        off += len(used)
    open(p("data", "hires.bin"), "wb").write(bytes(out))
    meta["layout"] = layout
    meta["built_from_compressed_mesh"] = True
    meta["per_surface_index"] = (
        "Each surface has its own index array, because the inflated and folded "
        "meshes are compressed separately and Draco gives them different vertex "
        "orders.")
    json.dump(meta, open(p("data", "hires.json"), "w", encoding="utf-8"), indent=1)
    print(f"  hires.bin rewritten, {len(out)/1e6:.2f} MB")


# --------------------------------------------------------------- cortex ----
def fix_cortex():
    import nibabel as nib
    meta = json.load(open(p("data", "surface.json"), encoding="utf-8"))
    NV = meta["surface"]["vertices_per_hemisphere"]
    NV = NV[0] if isinstance(NV, list) else NV
    raw = open(p("data", "surface-labels.bin"), "rb").read()
    idxs, counts = {}, {}
    for h in ("L", "R"):
        g = nib.load(p(".cache", f"S1200.{h}.midthickness.surf.gii"))
        v = np.asarray(g.darrays[0].data, np.float64)
        idxs[h], counts[h] = permutation(v, p("meshes", "cortex", f"{h}.glb"), h)
    out, sets = bytearray(), {}
    for key, s in meta["sets"].items():
        blocks = [np.frombuffer(raw, "<u2", NV, s["offset"] + hi * NV * 2)[idxs[h]]
                  .astype("<u2") for hi, h in enumerate(("L", "R"))]
        sets[key] = {**s, "offset": len(out),
                     "counts": [int(len(b)) for b in blocks],
                     "count": int(sum(len(b) for b in blocks))}
        for b in blocks:
            out += b.tobytes()
    open(p("data", "surface-labels.bin"), "wb").write(bytes(out))
    meta["sets"] = sets
    meta["surface"]["vertices_per_hemisphere"] = [counts["L"], counts["R"]]
    meta["built_from_compressed_mesh"] = True
    json.dump(meta, open(p("data", "surface.json"), "w", encoding="utf-8"), indent=1)
    print(f"  surface-labels.bin rewritten, {len(out)/1e6:.2f} MB")


if __name__ == "__main__":
    print("retinotopy"); fix_retinotopy()
    print("hires");      fix_hires()
    print("cortex");     fix_cortex()
