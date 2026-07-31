"""The blood vessels of the cubic millimetre.

The paper puts about 230 millimetres of vessel in this block, and the whole
segmented network ships as a single 6.9 MB Draco shard, which is small enough
that the page can simply have it.

The vessels are in the same 8x8x33 nm voxel frame as the cell bodies, so they
drop straight into the existing scene with no registration: the cells and the
plumbing that feeds them are already in one coordinate system.

Writes meshes/vessels/vessels.glb and its manifest.
"""

import json
import os

import numpy as np
import trimesh
from cloudvolume import CloudVolume

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLOUD = "gs://h01-release/data/20210601/blood_vessels_segmented"


def p(*a):
    q = os.path.join(ROOT, *a)
    os.makedirs(os.path.dirname(q), exist_ok=True)
    return q


cv = CloudVolume(CLOUD, use_https=True, progress=False)
props = cv.meta.info  # not the segment properties, just the volume header
print("resolution", cv.resolution, "bounds", cv.bounds)

# The release's own segment list for this layer.
import urllib.request, gzip
raw = urllib.request.urlopen(
    "https://storage.googleapis.com/h01-release/data/20210601/"
    "blood_vessels_segmented/segment_properties/info").read()
if raw[:2] == b"\x1f\x8b":
    raw = gzip.decompress(raw)
inline = json.loads(raw)["inline"]
ids = [int(i) for i in inline["ids"]]
tagprop = next((x for x in inline["properties"] if x["type"] == "tags"), None)
vocab = tagprop["tags"] if tagprop else []
tags_for = {}
if tagprop:
    for i, seg in enumerate(ids):
        tags_for[seg] = [vocab[t] for t in tagprop["values"][i]]
print(f"{len(ids)} vessel segments, tag vocabulary {vocab}")

# One fetch for the lot. Anything below a few hundred cubic micrometres is a
# fragment rather than a vessel and only costs geometry.
MIN_FACES = 60
parts, kept, dropped, missing = [], [], 0, []
# Not every id in segment_properties has a mesh manifest, and a single missing
# one aborts a batch fetch, so ask in small batches and record the gaps rather
# than losing the other 1,478.
BATCH = 64
for i in range(0, len(ids), BATCH):
    chunk = ids[i:i + BATCH]
    try:
        meshes = cv.mesh.get(chunk, lod=0)
    except Exception:
        meshes = {}
        for seg in chunk:
            try:
                meshes.update(cv.mesh.get(seg, lod=0))
            except Exception:
                missing.append(seg)
    for seg, m in meshes.items():
        if len(m.faces) < MIN_FACES:
            dropped += 1
            continue
        v = np.asarray(m.vertices, np.float64) / 1000.0    # nm to um
        parts.append(trimesh.Trimesh(vertices=v, faces=np.asarray(m.faces),
                                     process=False))
        kept.append({"id": int(seg), "faces": int(len(m.faces)),
                     "tags": tags_for.get(int(seg), [])})
    print(f"  {min(i+BATCH, len(ids)):5d}/{len(ids)}  kept {len(parts)}",
          flush=True)
print(f"{len(parts)} meshes kept, {dropped} fragments under {MIN_FACES} faces "
      f"dropped, {len(missing)} with no mesh manifest")

merged = trimesh.util.concatenate(parts)
out = p("meshes", "vessels", "vessels.glb")
merged.export(out)
ext = merged.bounds[1] - merged.bounds[0]
print(f"merged: {len(merged.faces):,} faces, "
      f"extent {ext[0]:.0f} x {ext[1]:.0f} x {ext[2]:.0f} um, "
      f"{os.path.getsize(out)/1e6:.1f} MB")

# The vessels have to sit in the same frame as the cell bodies or the whole
# point is lost. The soma table's bounding box is the check.
soma = json.load(open(p("data", "somas.json")))
lo, hi = np.array(soma["bounds_um"])
assert merged.bounds[0].min() > lo.min() - 200, merged.bounds
assert (merged.bounds[1] < hi + 200).all(), merged.bounds
print(f"frame check: vessels {merged.bounds[0].round(0)} to "
      f"{merged.bounds[1].round(0)}, cells {lo} to {hi}")

with open(p("meshes", "vessels", "manifest.json"), "w") as f:
    json.dump({
        "source": CLOUD,
        "citation": "Shapson-Coe et al., Science 384, eadk4858 (2024)",
        "note": "The paper reports about 230 mm of vessel and roughly 8,100 "
                "vessel-associated cells in this block. This is the segmented "
                "vasculature, merged into one mesh.",
        "segments_in_release": len(ids),
        "segments_drawn": len(kept),
        "fragments_dropped": dropped,
        "no_mesh_manifest": missing,
        "faces": int(len(merged.faces)),
        "extent_um": [round(float(v), 1) for v in ext],
        "file": "meshes/vessels/vessels.glb",
        "tag_vocabulary": vocab,
    }, f, indent=1)
print("wrote meshes/vessels/manifest.json")
