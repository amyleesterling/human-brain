"""Measure, from the H01 data already in this repo, the spatial scales the
scale map places things at.

The point of this file is that the boxes on that map are not drawn from
memory. Where H01 can measure something, H01 measures it, and the number that
ends up on the page is the one printed here. Where it cannot, the map carries a
citation instead and says so.

Writes data/scale-anchors.json.
"""

import json
import os

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def p(*a):
    return os.path.join(ROOT, *a)


meta = json.load(open(p("data", "somas.json")))
db = json.load(open(p("data", "cells.json")))
cells = db["cells"]

n = meta["count"]
buf = np.fromfile(p("data", "somas.bin"), dtype=np.uint8)
xyz = buf[: n * 12].view("<f4").reshape(n, 3)
depth = buf[n * 12: n * 16].view("<f4")

out = {
    "source": "measured from this repo's H01 data by scripts/scale_anchors.py",
    "citation": meta["citation"],
    "anchors": {},
}


def anchor(key, lo, hi, unit, how, typical=None):
    out["anchors"][key] = {
        "low": lo, "high": hi, "typical": typical, "unit": unit, "how": how,
    }
    t = f"  typical {typical:g}" if typical is not None else ""
    print(f"{key:26s} {lo:12.4g} .. {hi:12.4g} {unit}{t}")


# --- the block itself -------------------------------------------------------
lo, hi = np.array(meta["bounds_um"])
anchor("volume_block", float((hi - lo).min()), float((hi - lo).max()), "um",
       "bounding box of every cell body in the release's soma table")
anchor("cortical_thickness", 0.0, float(meta["cortex_depth_um"]), "um",
       "deepest reliable layer band, measured as distance to the pial surface",
       typical=float(meta["cortex_depth_um"]))

# --- cell body --------------------------------------------------------------
# The soma table gives positions, not sizes. Nearest neighbour distance between
# cell bodies is a real spacing measurement the table does support, and it is
# the number that says how tightly packed this tissue is.
from scipy.spatial import cKDTree

tree = cKDTree(xyz)
d, _ = tree.query(xyz, k=2)
nn = d[:, 1]
anchor("soma_spacing", float(np.percentile(nn, 5)), float(np.percentile(nn, 95)),
       "um", "distance from each cell body to its nearest neighbour, 5th to 95th "
       "percentile over all 49,379", typical=float(np.median(nn)))

# Cell density, which is the same fact stated the way people quote it.
vol_mm3 = float(np.prod(hi - lo)) / 1e9
out["anchors"]["cell_density"] = {
    "value": round(n / vol_mm3), "unit": "cell bodies per mm3",
    "how": f"{n} cell bodies in the {vol_mm3:.2f} mm3 bounding box",
}
print(f"{'cell_density':26s} {n / vol_mm3:12.4g} per mm3")

# --- the proofread cells ----------------------------------------------------
ext = np.array([c["bounds_um"][1] for c in cells]) - \
      np.array([c["bounds_um"][0] for c in cells])
longest = ext.max(axis=1)
anchor("arbor_extent", float(np.percentile(longest, 5)),
       float(np.percentile(longest, 95)), "um",
       "longest bounding box axis of each of the 104 proofread cells",
       typical=float(np.median(longest)))

vols = np.array([c["volume_um3"] for c in cells])
# Equivalent sphere diameter, which is the only size a volume can honestly be
# turned into. It is not a soma diameter: these are whole cells, arbor included.
eqd = 2 * (3 * vols / (4 * np.pi)) ** (1 / 3)
anchor("cell_volume", float(vols.min()), float(vols.max()), "um3",
       "reconstructed voxel count times the release's 8x8x33 nm voxel",
       typical=float(np.median(vols)))
anchor("cell_equivalent_diameter", float(eqd.min()), float(eqd.max()), "um",
       "diameter of a sphere of the same reconstructed volume",
       typical=float(np.median(eqd)))

# --- synapses ---------------------------------------------------------------
nsi = np.array([c["NSI"] for c in cells])
anchor("synapses_per_cell", float(nsi.min()), float(nsi.max()), "incoming synapses",
       "release property NSI over the 104 proofread cells",
       typical=float(np.median(nsi)))

# Spacing between synapses along a dendrite, from the release's own node counts.
# Skeleton nodes in this release are spaced at a fixed step, so the ratio of
# synapses to dendrite nodes is a density, not a length. Reported as the ratio
# it is rather than converted into a length nobody published.
sp = np.array([c["Sp"] for c in cells])
anchor("spinyness", float(sp.min()), float(sp.max()), "spines per dendrite node",
       "release property Sp over the 104 proofread cells",
       typical=float(np.median(sp)))

# --- what H01 counts but cannot size ---------------------------------------
out["not_measured_here"] = {
    "synaptic_cleft": "the release annotates 149,871,669 synapses but publishes "
                      "no cleft width, so the map cites the literature",
    "vesicle": "not segmented in this release",
    "ion_channel": "far below the 4 nm imaging resolution",
    "conduction_speed": "H01 is a fixed volume: it has no time axis at all",
}

with open(p("data", "scale-anchors.json"), "w") as f:
    json.dump(out, f, indent=1)
print("\nwrote data/scale-anchors.json")
