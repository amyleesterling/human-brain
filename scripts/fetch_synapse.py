"""One synapse, reconstructed from the electron microscopy.

The bottom rung of the scale ladder. Everything else on this site is millimetres
or micrometres; this is the thing all of it is made of, and in H01 it is a real
object you can pull out of the volume.

HOW. The release publishes every synapse on the 104 proofread cells, with the
location of the junction and of the partner on each side, in 8x8x33 nm voxels.
This picks one, pulls a small cube of the c3 segmentation around it at full
resolution, reads which segment sits on each side, and marching-cubes the two
partners into meshes.

WHAT IS REAL. The geometry is the segmentation's, at the resolution the
microscope worked at. What is NOT real is the smoothness: marching cubes on a
voxel grid then a light Laplacian smooth, because raw voxel meshes are stair
steps and the stairs are the grid, not the membrane.

Writes meshes/synapse/*.glb and data/synapse.json.
"""

import io
import json
import os
import urllib.request

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, ".cache")
B = "https://storage.googleapis.com/h01-release/data/20210601"
VOX = np.array([8.0, 8.0, 33.0])          # nanometres
HALF = np.array([190, 190, 46])           # voxels: about 3 x 3 x 3 micrometres


def p(*a):
    q = os.path.join(ROOT, *a)
    os.makedirs(os.path.dirname(q), exist_ok=True)
    return q


def main():
    from cloudvolume import CloudVolume
    from skimage import measure
    import trimesh

    csv = os.path.join(CACHE, "synapse_locations.csv")
    if not os.path.exists(csv):
        print("  downloading synapse_locations.csv (18 MB)")
        urllib.request.urlretrieve(f"{B}/proofread_104/synapse_locations.csv", csv)
    import pandas as pd
    syn = pd.read_csv(csv)
    syn.columns = [c.strip() for c in syn.columns]
    print(f"{len(syn):,} synapses on the 104 proofread cells")

    cells = json.load(open(p("data", "cells.json"), encoding="utf-8"))
    by = {c["id"]: c for c in cells["cells"]}

    cv = CloudVolume(f"gs://h01-release/data/20210601/c3", use_https=True,
                     progress=False, fill_missing=True)
    lo_all = np.array([0, 0, 0])
    hi_all = np.array(cv.bounds.maxpt)

    # Prefer a synapse where this cell is postsynaptic, on a well-fitted
    # pyramidal cell, and comfortably inside the block so the cube is full.
    cand = syn[syn["prepost"] == "post"].copy()
    cand["ok"] = True
    picked = None
    rng = np.random.default_rng(5)
    order = rng.permutation(len(cand))
    for j in order[:400]:
        r = cand.iloc[int(j)]
        c = by.get(str(int(r["104"])))
        if c is None or c.get("klass") != "pyramidal":
            continue
        xyz = np.array([r["x"], r["y"], r["z"]], int)
        if np.any(xyz - HALF < lo_all + 8) or np.any(xyz + HALF > hi_all - 8):
            continue
        pre = np.array([r["prex"], r["prey"], r["prez"]], int)
        post = np.array([r["postx"], r["posty"], r["postz"]], int)
        if np.array_equal(pre, post):
            continue
        picked = (r, xyz, pre, post, c)
        break
    if picked is None:
        raise SystemExit("no suitable synapse found")
    r, xyz, pre, post, cell = picked
    sep_nm = float(np.linalg.norm((pre - post) * VOX))
    print(f"  chose a synapse on segment {cell['id']} ({cell['klass']}, "
          f"{cell['layer']}) at voxel {tuple(xyz)}")
    print(f"  the two partner points are {sep_nm:.0f} nm apart")

    lo = xyz - HALF
    hi = xyz + HALF
    print(f"  pulling c3 at {tuple((hi-lo))} voxels "
          f"= {tuple(np.round((hi-lo)*VOX/1000, 2))} um")
    vol = cv[lo[0]:hi[0], lo[1]:hi[1], lo[2]:hi[2]]
    vol = np.asarray(vol)[..., 0]
    print(f"  got {vol.shape}, {len(np.unique(vol)):,} distinct segments in the cube")

    def seg_at(pt):
        q = pt - lo
        return int(vol[q[0], q[1], q[2]])

    seg_pre, seg_post = seg_at(pre), seg_at(post)
    print(f"  presynaptic segment  {seg_pre}")
    print(f"  postsynaptic segment {seg_post}")
    if seg_pre == 0 or seg_post == 0 or seg_pre == seg_post:
        raise SystemExit("the two sides did not resolve to distinct segments")

    out = []
    for name, seg, colour in (("presynaptic", seg_pre, "#FFB24D"),
                              ("postsynaptic", seg_post, "#3E96F0")):
        mask = (vol == seg)
        if mask.sum() < 200:
            raise SystemExit(f"{name} segment is only {mask.sum()} voxels")
        # Marching cubes in voxel space, then scale to micrometres, so the
        # anisotropic z is handled once and explicitly.
        v, f, _, _ = measure.marching_cubes(mask.astype(np.uint8), level=0.5)
        v = v * VOX / 1000.0
        m = trimesh.Trimesh(vertices=v, faces=f, process=True)
        m = trimesh.smoothing.filter_taubin(m, lamb=0.5, nu=-0.53, iterations=12)
        path = p("meshes", "synapse", f"{name}.glb")
        m.export(path)
        ext = m.bounds[1] - m.bounds[0]
        out.append({"role": name, "segment": seg, "colour": colour,
                    "voxels": int(mask.sum()),
                    "volume_um3": round(float(mask.sum() * np.prod(VOX) / 1e9), 3),
                    "faces": int(len(m.faces)),
                    "extent_um": [round(float(x), 2) for x in ext],
                    "file": f"meshes/synapse/{name}.glb",
                    "bytes": os.path.getsize(path)})
        print(f"  {name:13s} {mask.sum():7,} voxels, {len(m.faces):7,} faces, "
              f"{ext[0]:.2f} x {ext[1]:.2f} x {ext[2]:.2f} um, "
              f"{os.path.getsize(path)/1e6:.2f} MB")

    junction = (xyz - lo) * VOX / 1000.0
    doc = {
        "about": "One synapse from H01, reconstructed from the c3 segmentation "
                 "at the resolution the microscope worked at.",
        "citation": cells["citation"],
        "licence": "CC BY 4.0",
        "source": "gs://h01-release/data/20210601/c3, synapse from "
                  "proofread_104/synapse_locations.csv",
        "on_cell": {"segment": cell["id"], "class": cell["klass"],
                    "layer": cell["layer"],
                    "incoming_synapses": cell["NSI"]},
        "voxel_nm": VOX.tolist(),
        "cube_um": [round(float(x), 2) for x in (hi - lo) * VOX / 1000.0],
        "junction_um": [round(float(x), 3) for x in junction],
        "partner_separation_nm": round(sep_nm, 1),
        "smoothing": "Taubin, 12 iterations. Marching cubes on a voxel grid "
                     "gives stair steps, and the stairs are the grid rather "
                     "than the membrane. Nothing else is altered.",
        "parts": out,
    }
    with open(p("data", "synapse.json"), "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=1)
    print(f"\nwrote data/synapse.json")


if __name__ == "__main__":
    main()
