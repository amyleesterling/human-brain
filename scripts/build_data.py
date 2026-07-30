"""Turn the raw H01 pulls into the two files the page actually loads.

  data/somas.bin    49,379 cell bodies as packed binary, about 690 kB
  data/somas.json   the header for that binary: type and layer vocabularies
  data/cells.json   the 104 proofread cells, their release statistics, their
                    soma position and layer, and their mesh file

Run scripts/fetch_h01.py first. This step does no network work.
"""

import io
import json
import os
import struct
import urllib.request
import gzip

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUCKET = "https://storage.googleapis.com/h01-release/data/20210601"
VOXEL_NM = np.array([8.0, 8.0, 33.0])


def get(url):
    with urllib.request.urlopen(url) as r:
        raw = r.read()
    return gzip.decompress(raw) if raw[:2] == b"\x1f\x8b" else raw


def p(*parts):
    q = os.path.join(ROOT, *parts)
    os.makedirs(os.path.dirname(q), exist_ok=True)
    return q


df = pd.read_csv(io.BytesIO(get(f"{BUCKET}/c3/tables/somas.csv")))
xyz = df[["x", "y", "z"]].to_numpy(np.float64) * VOXEL_NM / 1000.0

types = sorted(df["celltype"].dropna().unique())
layers = ["Layer 1", "Layer 2", "Layer 3", "Layer 4", "Layer 5", "Layer 6",
          "White matter", "unclassified"]
ti = {t: i for i, t in enumerate(types)}
li = {l: i for i, l in enumerate(layers)}

tcode = np.array([ti.get(t, 255) for t in df["celltype"].fillna("")], np.uint8)
lcode = np.array([li.get(l, 255) for l in df["layer"].fillna("")], np.uint8)

# -------------------------------------------------------------------------
# Depth.
#
# Depth cannot be read off any axis of this volume. The block is a tilted slab
# and the cortical surface inside it is curved, so subtracting X smears layer 1
# across 2.7 mm and projecting onto a single fitted axis still smears it across
# 2.6 mm. Depth here is the true distance to the outward surface of the
# release's own layer 1 region, which is the tissue boundary the layers were
# segmented against. Measured that way the layer bands come out tight,
# monotonic and evenly spaced, and each layer's lower edge meets the next
# layer's upper edge to within about 30 um. That agreement is the check: no
# part of it was fitted to make it true.
#
# The one thing to distrust is the layer 1 band. Testing all 49,379 labels
# against all seven meshes, every label's best match is its own mesh, but
# Layer 1 is the weakest: 78 per cent of the cells carrying it fall inside the
# layer 1 mesh against 85 to 99 per cent for the others, and 7 per cent fall
# inside no layer mesh at all, out in the corners of the block. The label is
# doing some duty as a catch-all, so the surface derived from that region is
# close to the pia rather than exactly it.
import trimesh

LAYER_FILES = ["layer1", "layer2", "layer3", "layer4", "layer5", "layer6",
               "white-matter"]
_m = {n: trimesh.load(p("meshes", "layers", n + ".glb"), force="mesh")
      for n in LAYER_FILES}
_cent = np.array([np.asarray(_m[n].vertices).mean(0) for n in LAYER_FILES])
_axis = np.linalg.svd(_cent - _cent.mean(0))[2][0]
if np.dot(_cent[-1] - _cent[0], _axis) < 0:
    _axis = -_axis
# Faces of the layer 1 slab that look out of the brain. The slab is also cut by
# the block on its sides, and those rim faces point sideways, so requiring a
# strong outward component drops them.
_l1 = _m["layer1"]
_out = np.where(_l1.face_normals @ (-_axis) > 0.55)[0]
_pia = _l1.submesh([_out], append=True)
print(f"pia patch: {len(_out)} of {len(_l1.faces)} layer 1 faces, "
      f"{_pia.area/1e6:.3f} mm2")
depth = -trimesh.proximity.ProximityQuery(_pia).signed_distance(xyz)
print(f"depth: p1 {np.percentile(depth,1):.0f}, median {np.median(depth):.0f}, "
      f"p99 {np.percentile(depth,99):.0f} um; "
      f"{(depth < 0).sum()} somas sit outside the surface")

# -------------------------------------------------------------------------
# The binary the page loads: xyz then depth as float32, then one byte of class
# and one of layer, so the page parses it with four typed-array views and no
# loop. 255 means unlabelled.
with open(p("data", "somas.bin"), "wb") as f:
    f.write(xyz.astype("<f4").tobytes())
    f.write(depth.astype("<f4").tobytes())
    f.write(tcode.tobytes())
    f.write(lcode.tobytes())

counts_type = {t: int((df["celltype"] == t).sum()) for t in types}
counts_layer = {l: int((df["layer"] == l).sum()) for l in layers}

# Which of the eleven classes in this table count as neurons.
#
# This grouping is not a guess. It is the one that reproduces the paper's own
# figures from the table exactly: 8803 + 4688 + 1535 + 193 + 868 = 16,087
# neurons, which is the paper's neuron count to the cell, and the spiny subset
# 8803 + 1535 + 193 = 10,531, which is its spiny count to the cell. C_SHAPED
# is the class that decides it: counted as a neuron the total comes to 16,253
# and matches nothing, counted with the glia the glial total comes to
# 20,139 + 6,536 + 5,474 + 166 = 32,315, which is the paper's glial count to
# the cell. So the paper groups the C shaped cells with glia, and this file
# follows the paper rather than the intuition that a named cell class with a
# shape is a neuron.
NEURONAL = {"PYRAMIDAL", "INTERNEURON", "SPINY_STELLATE", "SPINY_ATYPICAL",
            "UNCLASSIFIED_NEURON"}
GLIAL = {"OLIGO", "ASTROCYTE", "MG_OPC", "C_SHAPED"}
SPINY = {"PYRAMIDAL", "SPINY_ATYPICAL", "SPINY_STELLATE"}

meta = {
    "source": "gs://h01-release/data/20210601/c3/tables/somas.csv",
    "citation": "Shapson-Coe et al., Science 384, eadk4858 (2024)",
    "bin": "data/somas.bin",
    "count": int(len(df)),
    "units": "micrometres",
    "layout": [
        {"field": "xyz", "type": "float32", "components": 3, "offset": 0},
        {"field": "depth", "type": "float32", "offset": int(len(df) * 12)},
        {"field": "type", "type": "uint8", "offset": int(len(df) * 16)},
        {"field": "layer", "type": "uint8", "offset": int(len(df) * 17)},
    ],
    "types": types,
    "neuronal": sorted(NEURONAL),
    "layers": layers,
    "glial": sorted(GLIAL),
    "counts": {"type": counts_type, "layer": counts_layer},
    "neuron_count": int(sum(counts_type[t] for t in types if t in NEURONAL)),
    "glia_count": int(sum(counts_type[t] for t in types if t in GLIAL)),
    "spiny_count": int(sum(counts_type[t] for t in types if t in SPINY)),
    # The paper's own figures, so the page can show that the table reproduces
    # them rather than asking the reader to take the grouping on trust.
    "paper": {
        "neurons": 16087, "glia": 32315, "spiny": 10531,
        "citation": "Shapson-Coe et al., Science 384, eadk4858 (2024)",
    },
    "bounds_um": [xyz.min(0).round(1).tolist(), xyz.max(0).round(1).tolist()],
    "depth_reference": (
        "distance to the outward surface of the release's layer 1 region, "
        f"a {_pia.area/1e6:.2f} mm2 patch of {len(_out)} faces from "
        "gs://h01-release/data/20210601/layers"
    ),
}

# Where each layer sits, as depth below that surface. Taken as the 5th to 95th
# percentile of its own cell bodies rather than the full range, so that a
# handful of stray assignments cannot smear a band across the whole cortex.
# This is what the depth ladder on the page is drawn from.
bands = []
for l in layers[:7]:
    m = lcode == li[l]
    if m.sum() < 20:
        continue
    d = depth[m]
    b = {
        "layer": l,
        "top_um": round(float(np.percentile(d, 5)), 1),
        "bottom_um": round(float(np.percentile(d, 95)), 1),
        "median_um": round(float(np.median(d)), 1),
        "count": int(m.sum()),
    }
    # Layer 1 is the one band that does not hold up, and the page must not draw
    # it as though it did. Its cells run from above the surface to 2 mm down,
    # deeper than layer 6, because the label is doing duty as a catch-all for
    # cell bodies that fall outside every layer region.
    if l == "Layer 1":
        b["reliable"] = False
        b["note"] = (
            "not drawn: 7 per cent of the cells carrying this label lie inside "
            "no layer mesh at all, and 16 per cent lie deeper than layer 4, so "
            "the band spans almost the whole cortex"
        )
    bands.append(b)
meta["layer_bands"] = bands
meta["cortex_depth_um"] = round(
    max(b["bottom_um"] for b in bands if b.get("reliable", True)), 1)
# The check that the depth measure is sound: each layer's lower edge should
# meet the next layer's upper edge. Printed so a regression is visible rather
# than quiet, and carried in the file so the page can quote it.
good = [b for b in bands if b.get("reliable", True)]
gaps = [round(good[i + 1]["top_um"] - good[i]["bottom_um"], 1)
        for i in range(len(good) - 1)]
meta["band_seam_um"] = gaps
with open(p("data", "somas.json"), "w") as f:
    json.dump(meta, f, indent=1)
print(f"somas.bin {os.path.getsize(p('data','somas.bin'))/1e3:.0f} kB, "
      f"{len(df)} cells")
for k in ("neuron", "glia", "spiny"):
    got = meta[f"{k}_count"] if k != "neuron" else meta["neuron_count"]
    want = meta["paper"][{"neuron": "neurons", "glia": "glia", "spiny": "spiny"}[k]]
    print(f"  {k:8s} table {got:6d}  paper {want:6d}  "
          f"{'match' if got == want else 'MISMATCH'}")
for b in bands:
    print(f"  {b['layer']:14s} {b['top_um']:7.0f} - {b['bottom_um']:7.0f} um"
          f"   median {b['median_um']:7.0f}   n={b['count']}")
print(f"  seams between consecutive layers, layer 2 down: {gaps} um")

# -------------------------------------------------------------------------
# The 104 proofread cells: release statistics joined to soma and mesh.
info = json.loads(get(f"{BUCKET}/proofread_104/segment_properties/info"))["inline"]
tagprop = next(x for x in info["properties"] if x["type"] == "tags")
vocab = tagprop["tags"]
nums = {x["id"]: x for x in info["properties"] if x["type"] == "number"}

# Row index rather than the row, so the depth computed above can be looked up
# for the same soma instead of recomputed from a copy of its coordinates.
soma_by_seg = {}
for i, v in enumerate(df["proofread_104_rep"]):
    if not pd.isna(v):
        soma_by_seg.setdefault(str(int(v)), i)

meshman = json.load(open(p("meshes", "cells", "manifest.json")))["cells"]
mesh_by_id = {m["id"]: m for m in meshman}

cells = []
for i, seg in enumerate(info["ids"]):
    tags = [vocab[t] for t in tagprop["values"][i]]
    si = soma_by_seg.get(seg)
    m = mesh_by_id.get(seg)
    c = {
        "id": seg,
        "tags": tags,
        # The layer and class tags are the first ones in the vocabulary, so
        # pull them out by membership rather than by position.
        "layer": next((t for t in tags if t in
                       {"L1", "L2", "L3", "L4", "L5", "L6", "WM"}), None),
        "klass": next((t for t in tags if t in
                       {"pyramidal", "interneuron", "spiny-stellate", "astrocyte",
                        "oligodendrocyte", "microglia/opc", "blood-vessel-cell",
                        "c-shaped", "unclassified-neuron", "unknown-type",
                        "excitatory/spiny-with-atypical-tree"}), None),
        **{k: v["values"][i] for k, v in nums.items()},
    }
    if si is not None:
        c["soma_um"] = [round(float(v), 1) for v in xyz[si]]
        c["soma_depth_um"] = round(float(depth[si]), 1)
        sl, sc = df["layer"].iloc[si], df["celltype"].iloc[si]
        c["soma_layer"] = None if pd.isna(sl) else sl
        c["soma_celltype"] = None if pd.isna(sc) else sc
    if m is not None:
        c["mesh"] = m["file"]
        c["faces"] = m["faces"]
        c["bounds_um"] = m["bounds_um"]
        c["bytes"] = os.path.getsize(p(m["file"]))
    cells.append(c)

# Volume in cubic micrometres, from the release's own voxel count.
vox_um3 = float(VOXEL_NM.prod()) / 1e9
for c in cells:
    c["volume_um3"] = round(c["NVx"] * vox_um3, 1)

out = {
    "source": "gs://h01-release/data/20210601/proofread_104",
    "citation": "Shapson-Coe et al., Science 384, eadk4858 (2024)",
    "mesh_lod": 3,
    # The page's depth ladder is drawn from these, so they travel with the
    # cells rather than being fetched from the soma header separately.
    "layer_bands": bands,
    "cortex_depth_um": meta["cortex_depth_um"],
    "fields": {k: v.get("description", "") for k, v in nums.items()},
    "derived": {
        "volume_um3": "NVx x 8x8x33 nm, the release's own voxel size",
        "soma_um": "position of this cell's soma in c3/tables/somas.csv",
        "soma_depth_um": meta["depth_reference"],
    },
    "tag_vocabulary": vocab,
    "cells": cells,
}
with open(p("data", "cells.json"), "w") as f:
    json.dump(out, f, indent=1)

withmesh = sum(1 for c in cells if "mesh" in c)
withsoma = sum(1 for c in cells if "soma_um" in c)
print(f"cells.json {len(cells)} cells, {withmesh} with a mesh, {withsoma} with a soma")
print("  total faces", f"{sum(c.get('faces',0) for c in cells):,}",
      "| total mesh", f"{sum(c.get('bytes',0) for c in cells)/1e6:.1f} MB")
