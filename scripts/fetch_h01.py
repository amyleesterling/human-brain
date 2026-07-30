"""Pull the H01 human cortex data this site is built on.

H01 is one cubic millimetre of human temporal cortex, resected during epilepsy
surgery, imaged by serial section electron microscopy at 4 nm and reconstructed
by Google Connectomics. Shapson-Coe et al., Science 384, eadk4858 (2024).

Everything here comes from the public bucket gs://h01-release, read anonymously
over https. Nothing is approximated: if a number is not in the release, this
site does without it.

Outputs, all under the repo root:
  data/somas.json         every cell body in the volume, position + type + layer
  data/cells.json         the 104 proofread cells and their release statistics
  meshes/layers/*.glb     the six cortical layers and white matter, as surfaces
  meshes/cells/*.glb      the 104 proofread cells

Usage:
  python scripts/fetch_h01.py somas
  python scripts/fetch_h01.py layers
  python scripts/fetch_h01.py cells [--lod 3]
"""

import argparse
import gzip
import io
import json
import os
import sys
import urllib.request

import numpy as np

BUCKET = "https://storage.googleapis.com/h01-release/data/20210601"
CLOUDPATH = "gs://h01-release/data/20210601"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The segmentation is indexed in 8x8x33 nm voxels. Every coordinate this script
# writes out is converted to micrometres so the page never has to know that.
VOXEL_NM = np.array([8.0, 8.0, 33.0])


def get(url):
    with urllib.request.urlopen(url) as r:
        raw = r.read()
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return raw


def out(*parts):
    p = os.path.join(ROOT, *parts)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    return p


# ---------------------------------------------------------------- somas ----
def fetch_somas():
    """c3/tables/somas.csv: 49,379 cell bodies, each with a type and a layer."""
    import pandas as pd

    raw = get(f"{BUCKET}/c3/tables/somas.csv")
    df = pd.read_csv(io.BytesIO(raw))
    print(f"somas.csv: {len(df)} rows")

    xyz_um = df[["x", "y", "z"]].to_numpy(dtype=np.float64) * VOXEL_NM / 1000.0

    types = sorted(t for t in df["celltype"].dropna().unique())
    layers = sorted(l for l in df["layer"].dropna().unique())
    ti = {t: i for i, t in enumerate(types)}
    li = {l: i for i, l in enumerate(layers)}

    payload = {
        "source": "gs://h01-release/data/20210601/c3/tables/somas.csv",
        "citation": "Shapson-Coe et al., Science 384, eadk4858 (2024)",
        "count": int(len(df)),
        "units": "micrometres",
        "voxel_nm": VOXEL_NM.tolist(),
        "types": types,
        "layers": layers,
        # Positions are quantised to 0.1 um, which is far finer than a soma and
        # cuts the file by more than half against full float text.
        "xyz": [[round(v, 1) for v in row] for row in xyz_um],
        "type": [ti.get(t, -1) for t in df["celltype"].fillna("")],
        "layer": [li.get(l, -1) for l in df["layer"].fillna("")],
        # 111 of the somas belong to one of the 104 proofread cells.
        "proofread": {
            str(int(r.proofread_104_rep)): i
            for i, r in enumerate(df.itertuples())
            if not pd.isna(r.proofread_104_rep)
        },
    }
    path = out("data", "somas.json")
    with open(path, "w") as f:
        json.dump(payload, f, separators=(",", ":"))
    print(f"wrote {path} ({os.path.getsize(path)/1e6:.1f} MB)")
    for t in types:
        print(f"  {t:24s} {int((df.celltype == t).sum()):6d}")


# ---------------------------------------------------------------- cells ----
def fetch_cell_table():
    """proofread_104/segment_properties: the release's own per-cell numbers."""
    info = json.loads(get(f"{BUCKET}/proofread_104/segment_properties/info"))
    inline = info["inline"]
    ids = inline["ids"]

    tagprop = next(p for p in inline["properties"] if p["type"] == "tags")
    vocab = tagprop["tags"]
    numeric = {
        p["id"]: {"values": p["values"], "description": p.get("description", "")}
        for p in inline["properties"]
        if p["type"] == "number"
    }

    cells = []
    for i, seg in enumerate(ids):
        tags = [vocab[t] for t in tagprop["values"][i]]
        cells.append(
            {
                "id": seg,
                "tags": tags,
                **{k: v["values"][i] for k, v in numeric.items()},
            }
        )

    payload = {
        "source": "gs://h01-release/data/20210601/proofread_104",
        "citation": "Shapson-Coe et al., Science 384, eadk4858 (2024)",
        "fields": {k: v["description"] for k, v in numeric.items()},
        "tag_vocabulary": vocab,
        "cells": cells,
    }
    path = out("data", "cells.json")
    with open(path, "w") as f:
        json.dump(payload, f, indent=1)
    print(f"wrote {path}: {len(cells)} proofread cells")
    return [int(i) for i in ids]


# --------------------------------------------------------------- meshes ----
def to_glb(vertices_um, faces, path):
    import trimesh

    m = trimesh.Trimesh(vertices=vertices_um, faces=faces, process=False)
    m.export(path)


def fetch_layers():
    """layers/mesh: cortical layers 1 to 6 plus white matter, as surfaces."""
    from cloudvolume import CloudVolume

    cv = CloudVolume(f"{CLOUDPATH}/layers", use_https=True, progress=False)
    names = {1: "layer1", 2: "layer2", 3: "layer3", 4: "layer4",
             5: "layer5", 6: "layer6", 7: "white-matter"}
    manifest = []
    for seg, name in names.items():
        m = cv.mesh.get(seg)[seg]
        # cloudvolume returns these already in nanometres.
        v = np.asarray(m.vertices, dtype=np.float64) / 1000.0
        path = out("meshes", "layers", f"{name}.glb")
        to_glb(v, np.asarray(m.faces), path)
        manifest.append(
            {
                "id": seg,
                "name": name,
                "file": f"meshes/layers/{name}.glb",
                "vertices": int(len(v)),
                "faces": int(len(m.faces)),
                "bounds_um": [v.min(0).round(1).tolist(), v.max(0).round(1).tolist()],
                "bytes": os.path.getsize(path),
            }
        )
        print(f"  {name:14s} {len(v):7d} verts  {os.path.getsize(path)/1e3:7.0f} kB")
    with open(out("meshes", "layers", "manifest.json"), "w") as f:
        json.dump({"source": f"{CLOUDPATH}/layers", "layers": manifest}, f, indent=1)


def fetch_cells(lod):
    """proofread_104/mesh at a given level of detail.

    lod 0 is roughly 2.7 million faces per cell, which no browser wants. lod 3
    is roughly 22 thousand and still carries every branch, because the multires
    levels simplify geometry rather than prune the arbor.
    """
    from cloudvolume import CloudVolume

    ids = fetch_cell_table()
    cv = CloudVolume(f"{CLOUDPATH}/proofread_104", use_https=True, progress=False)
    manifest = []
    for n, seg in enumerate(ids, 1):
        path = out("meshes", "cells", f"{seg}.glb")
        if os.path.exists(path):
            continue
        try:
            m = cv.mesh.get(seg, lod=lod)[seg]
        except Exception as e:
            print(f"  {seg}: FAILED {type(e).__name__} {e}")
            continue
        v = np.asarray(m.vertices, dtype=np.float64) / 1000.0
        to_glb(v, np.asarray(m.faces), path)
        manifest.append(
            {
                "id": str(seg),
                "file": f"meshes/cells/{seg}.glb",
                "lod": lod,
                "vertices": int(len(v)),
                "faces": int(len(m.faces)),
                "bounds_um": [v.min(0).round(1).tolist(), v.max(0).round(1).tolist()],
                "bytes": os.path.getsize(path),
            }
        )
        print(f"  [{n:3d}/{len(ids)}] {seg} {len(m.faces):7d} faces "
              f"{os.path.getsize(path)/1e3:7.0f} kB", flush=True)
    with open(out("meshes", "cells", "manifest.json"), "w") as f:
        json.dump({"source": f"{CLOUDPATH}/proofread_104", "lod": lod,
                   "cells": manifest}, f, indent=1)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=["somas", "layers", "cells", "table"])
    ap.add_argument("--lod", type=int, default=3)
    a = ap.parse_args()
    {"somas": fetch_somas, "layers": fetch_layers, "table": fetch_cell_table,
     "cells": lambda: fetch_cells(a.lod)}[a.what]()
