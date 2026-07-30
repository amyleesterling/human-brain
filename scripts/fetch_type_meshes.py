"""Export the eleven representative cells chosen by pick_type_examples.py.

Run pick_type_examples.py first. That script decides WHICH cell stands for each
class and why; this one only fetches the meshes it named and measures what the
page will print beside them.

Every one of these is a c3 agglomeration segment and none is proofread. The
manifest carries that flag so the page cannot forget to say so.
"""

import json
import os

import numpy as np
import trimesh
from cloudvolume import CloudVolume

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLOUD = "gs://h01-release/data/20210601/c3"

# Level of detail is chosen per cell, not once for all eleven. These cells do
# not have comparable complexity: a whole astrocyte is 1.4 million faces at the
# same level where an oligodendrocyte is ten thousand, because an astrocyte's
# job is surface area. One level for everything either ships 55 MB or erases
# the small cells. The rule is the coarsest level that still carries at least
# MIN_FACES, preferring to stay under MAX_FACES.
MIN_FACES = 12_000
MAX_FACES = 150_000
LODS = [4, 3, 2, 1, 0]


def choose_lod(cv, seg):
    """Returns (mesh, lod, tried) with the coarsest acceptable level."""
    tried = {}
    best = None
    for lod in LODS:
        try:
            m = cv.mesh.get(seg, lod=lod)[seg]
        except Exception:
            continue
        f = len(m.faces)
        tried[lod] = f
        if MIN_FACES <= f <= MAX_FACES:
            return m, lod, tried
        # Remember the finest one seen in case nothing lands in the window.
        if best is None or abs(f - 60_000) < abs(len(best[0].faces) - 60_000):
            best = (m, lod)
    if best is None:
        raise RuntimeError(f"no mesh for {seg}")
    return best[0], best[1], tried


def p(*a):
    q = os.path.join(ROOT, *a)
    os.makedirs(os.path.dirname(q), exist_ok=True)
    return q


db = json.load(open(p("data", "type-examples.json")))
soma = json.load(open(p("data", "somas.json")))
cv = CloudVolume(CLOUD, use_https=True, progress=False)

# Depth of every class, measured from the soma table, so the gallery can say
# where each kind of cell actually sits rather than where it is said to sit.
n = soma["count"]
buf = np.fromfile(p("data", "somas.bin"), dtype=np.uint8)
depth = buf[n * 12: n * 16].view("<f4")
tcode = buf[n * 16: n * 17]
types = soma["types"]

out = []
for ex in db["examples"]:
    c = ex["chosen"]
    seg = c["seg"]
    m, lod, tried = choose_lod(cv, seg)
    v = np.asarray(m.vertices, np.float64) / 1000.0
    path = p("meshes", "types", f"{seg}.glb")
    trimesh.Trimesh(vertices=v, faces=np.asarray(m.faces), process=False).export(path)

    ti = types.index(ex["class"])
    d = depth[tcode == ti]
    rec = {
        "class": ex["class"], "label": ex["label"], "id": str(seg),
        "file": f"meshes/types/{seg}.glb",
        "faces": int(len(m.faces)),
        "lod": lod, "faces_by_lod": {str(k): v for k, v in sorted(tried.items())},
        "bytes": os.path.getsize(path),
        "extent_um": c["extent_um"],
        "longest_um": round(c["longest_um"], 1),
        "soma_um": c["soma_um"], "soma_vox": c["soma_vox"],
        "layer": c["layer"],
        "count": soma["counts"]["type"][ex["class"]],
        "share_pct": round(100 * soma["counts"]["type"][ex["class"]] / n, 1),
        "depth_um": {
            "p10": round(float(np.percentile(d, 10)), 0),
            "median": round(float(np.median(d)), 0),
            "p90": round(float(np.percentile(d, 90)), 0),
        },
        "sampled_range_um": ex["spread_longest_um"],
        "population_in_block": ex["population_in_block"],
        "neuroglancer": ex["neuroglancer"],
        "proofread": False,
    }
    out.append(rec)
    print(f"  {ex['label']:26s} lod {lod}  {int(len(m.faces)):7d} faces  "
          f"{os.path.getsize(path)/1e6:5.2f} MB  depth median "
          f"{rec['depth_um']['median']:5.0f} um   available {tried}")

with open(p("meshes", "types", "manifest.json"), "w") as f:
    json.dump({
        "source": CLOUD,
        "mesh_lod": "chosen per cell, see faces_by_lod on each",
        "proofread": False,
        "warning": "c3 agglomeration segments. None of these is proofread and "
                   "any may contain a merge or a split. Chosen as the median "
                   "of a sample; see scripts/pick_type_examples.py.",
        "selection": db["selection"],
        "citation": db["citation"],
        "types": out,
    }, f, indent=1)
print(f"\n{len(out)} meshes, "
      f"{sum(r['bytes'] for r in out)/1e6:.1f} MB before compression")
