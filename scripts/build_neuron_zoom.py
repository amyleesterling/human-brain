"""Close the gap between a neuron and a synapse.

THE PROBLEM. The ladder went from a 2.13 mm neuron straight to a 3.04 um
synapse: a single step of 701 times, where every other step near it is under
six. Worse, it was not even the same object. The neuron rung was segment
5015035926 and the synapse was on 3470629528, so the zoom flew into one cell
and landed on a junction belonging to a different one. Nothing on screen said
so, which is exactly why it needed saying.

THE FIX. Use the cell the synapse is actually on, and crop that one mesh at
decreasing sizes around the synapse's own position, so the descent is one
continuous push into one place on one cell: whole cell, a branch, a length of
dendrite, then the junction itself.

Cropping is by face centroid rather than by clipping planes. A clipped mesh
gets flat caps where the planes cut it, and a dendrite sliced off square looks
like a cut cable; keeping whole faces leaves the ragged end an actual broken
branch has.

Writes meshes/neuron/*.glb and data/neuron-zoom.json.
"""

import json
import os
import subprocess
import tempfile

import numpy as np
import trimesh

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Widths in micrometres, chosen so every step is about four times, which is
# what the rest of the ladder does.
CROPS = [
    (300.0, "A branch of it",
     "One dendrite leaving the cell body, with its side branches."),
    (80.0, "A length of dendrite",
     "Eighty micrometres of cable. Somewhere on this stretch is the junction "
     "the next rung shows."),
    (20.0, "Where the synapse is",
     "Twenty micrometres. The swellings on the surface are where other cells "
     "arrive; this cell carries 3,117 of them."),
]


def p(*a):
    q = os.path.join(ROOT, *a)
    os.makedirs(os.path.dirname(q), exist_ok=True)
    return q


def decoded(glb):
    """Vertices in the order the browser will see them, past Draco."""
    tmp = os.path.join(tempfile.mkdtemp(), "d.glb")
    subprocess.run(["npx", "--yes", "@gltf-transform/cli@latest", "cp", glb, tmp],
                   check=True, shell=True, capture_output=True)
    return trimesh.load(tmp, force="mesh", process=False)


def main():
    syn = json.load(open(p("data", "synapse.json"), encoding="utf-8"))
    cells = json.load(open(p("data", "cells.json"), encoding="utf-8"))
    seg = str(syn["on_cell"]["segment"])
    cell = next(c for c in cells["cells"] if str(c["id"]) == seg)
    centre = np.array(syn["centre_um"], float)
    print(f"synapse on segment {seg} ({cell['klass']}, {cell['layer']}, "
          f"{cell['NSI']:,} incoming) at {centre} um")

    # The shipped cell meshes are level of detail 3, about 22,000 faces for a
    # whole neuron. That is right for drawing an entire arbor and far too
    # coarse for a twenty micrometre crop: the first attempt returned 316
    # faces, which is a dendrite drawn as a handful of flat plates. Pull this
    # one cell at lod 1 instead. Only the crops ship, so the fine mesh costs
    # nothing on the page.
    fine = p(".cache", f"{seg}_lod1.glb")
    if not os.path.exists(fine):
        from cloudvolume import CloudVolume
        print("  fetching this cell at lod 1 ...")
        cv = CloudVolume("gs://h01-release/data/20210601/proofread_104",
                         use_https=True, progress=False)
        fm = cv.mesh.get(int(seg), lod=1)[int(seg)]
        trimesh.Trimesh(np.asarray(fm.vertices, float) / 1000.0,
                        np.asarray(fm.faces)).export(fine)
    m = trimesh.load(fine, force="mesh", process=False)
    coarse = decoded(p(*cell["mesh"].split("/")))
    print(f"  lod 3 {len(coarse.faces):,} faces -> lod 1 {len(m.faces):,} faces")
    v = np.asarray(m.vertices)
    lo, hi = v.min(0), v.max(0)
    print(f"  mesh {len(m.faces):,} faces, extent {np.round(hi - lo, 1)} um, "
          f"origin {np.round(lo, 1)}")

    # THE FRAME CHECK. The mesh could be in absolute micrometres, or centred, or
    # in nanometres, and all three would export a plausible-looking crop. The
    # synapse must land inside this cell's own bounding box, because it is a
    # synapse on this cell.
    inside_bb = bool(np.all(centre > lo - 5) and np.all(centre < hi + 5))
    print(f"  synapse inside the mesh bounding box: {inside_bb}")
    assert inside_bb, (
        f"the synapse at {centre} is not inside the mesh bounds "
        f"{np.round(lo,1)} to {np.round(hi,1)}, so the two are not in the same "
        f"frame and every crop below would be of the wrong piece of cell")

    # And a tighter one: the nearest bit of actual surface must be close. A
    # point can sit inside a bounding box and still be nowhere near the cell,
    # because a neuron fills very little of its own box.
    d_near = float(np.linalg.norm(v - centre, axis=1).min())
    print(f"  nearest surface vertex is {d_near:.2f} um from the synapse")
    assert d_near < 3.0, (
        f"the closest the cell surface comes to this synapse is {d_near:.1f} um, "
        f"which is not a contact; the location is wrong")

    tri = v[m.faces].mean(axis=1)          # face centroids
    out = []
    for width, name, note in CROPS:
        h = width / 2.0
        keep = np.all(np.abs(tri - centre) <= h, axis=1)
        assert keep.sum() > 2000, (
            f"only {keep.sum()} faces within {width} um of the synapse, which "
            f"is not enough to draw")
        sub = m.submesh([np.nonzero(keep)[0]], append=True)
        before = len(sub.faces)
        if before > 70_000:
            try:
                sub = sub.simplify_quadric_decimation(face_count=70_000)
            except Exception:
                pass
        sv = np.asarray(sub.vertices)
        ext = sv.max(0) - sv.min(0)
        path = p("meshes", "neuron", f"crop{int(width)}.glb")
        sub.export(path)
        out.append({
            "id": f"nz{int(width)}", "name": name, "note": note,
            "file": f"meshes/neuron/crop{int(width)}.glb",
            "width_um": width,
            "width_m": round(width / 1e6, 9),
            "faces": int(len(sub.faces)),
            "faces_before_decimation": int(before),
            "actual_extent_um": [round(float(x), 1) for x in ext],
            "bytes": os.path.getsize(path),
        })
        print(f"  {width:6.0f} um  {before:7,} -> {len(sub.faces):7,} faces  "
              f"extent {np.round(ext,1)}  {os.path.getsize(path)/1e6:5.2f} MB")

    # The crops must actually get smaller, and each must still be a piece of
    # cell rather than a scattering of stray triangles.
    ws = [o["width_um"] for o in out]
    assert all(a > b for a, b in zip(ws, ws[1:])), ws
    for o in out:
        assert max(o["actual_extent_um"]) > o["width_um"] * 0.25, (
            f"the {o['width_um']} um crop only spans "
            f"{max(o['actual_extent_um'])} um of real geometry, so the cell "
            f"barely passes through this box and it would look empty")

    full_um = float(max(hi - lo))
    steps = [full_um] + ws + [max(syn["cube_um"])]
    print("\n  the bottom of the ladder now steps:")
    for a, b in zip(steps, steps[1:]):
        print(f"    {a:8.1f} -> {b:8.2f} um   {a/b:6.1f}x")

    doc = {
        "about": "The gap between a whole neuron and one synapse, filled by "
                 "cropping the same cell around the synapse's own position.",
        "cell": {"segment": seg, "class": cell["klass"], "layer": cell["layer"],
                 "incoming_synapses": cell["NSI"],
                 "full_extent_um": [round(float(x), 1) for x in (hi - lo)],
                 "full_width_um": round(full_um, 1),
                 "full_width_m": round(full_um / 1e6, 9),
                 "mesh": cell["mesh"]},
        "synapse_centre_um": [round(float(x), 2) for x in centre],
        "nearest_surface_um": round(d_near, 2),
        "why": "The ladder used to go from a 2.13 mm neuron to a 3.04 um "
               "synapse in one step of 701 times, and the neuron was not even "
               "the cell the synapse is on. Now it is, and the descent is one "
               "continuous push into one place on one cell.",
        "method": "Faces whose centroid falls inside a box of the given width "
                  "around the synapse. Whole faces rather than clipping "
                  "planes: a clipped dendrite gets a flat cap and reads as a "
                  "cut cable, where a ragged end reads as a broken branch.",
        "crops": out,
    }
    with open(p("data", "neuron-zoom.json"), "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=1)
    print("\nwrote data/neuron-zoom.json")


if __name__ == "__main__":
    main()
