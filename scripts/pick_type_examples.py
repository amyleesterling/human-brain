"""Choose one representative cell of every class in H01, and say why.

These are the cells a type gallery would show, and none of them are proofread:
they come from the c3 automatic agglomeration, so any of them may carry a merge
or a split. This script exists so that the choice is defensible and so the list
can be handed to someone who might proofread them.

THE SELECTION RULE. For each class, sample candidates, pull the mesh, measure
its longest axis, and take the one closest to that class's own median. Taking
the first cell that loads is how you end up showing a merged blob and calling it
a typical astrocyte. Only cells whose soma sits well inside the block are
considered, because a soma near a face has a truncated arbor.

Writes data/type-examples.json and PROOFREADING-REQUEST.md.
"""

import io
import json
import os
import urllib.request

import numpy as np
import pandas as pd
from cloudvolume import CloudVolume

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
B = "https://storage.googleapis.com/h01-release/data/20210601"
CLOUD = "gs://h01-release/data/20210601/c3"
VOXEL_NM = np.array([8.0, 8.0, 33.0])

CANDIDATES = 11          # meshes pulled per class before choosing
LOD = 2
NG = "https://h01-dot-neuroglancer-demo.appspot.com/#!"

LABEL = {
    "PYRAMIDAL": "Pyramidal cell", "INTERNEURON": "Interneuron",
    "SPINY_STELLATE": "Spiny stellate cell",
    "SPINY_ATYPICAL": "Spiny cell, atypical tree",
    "UNCLASSIFIED_NEURON": "Neuron, unclassified", "OLIGO": "Oligodendrocyte",
    "ASTROCYTE": "Astrocyte", "MG_OPC": "Microglia or OPC",
    "C_SHAPED": "C shaped cell", "BLOOD_VESSEL_CELL": "Blood vessel cell",
    "UNKNOWN": "Unknown",
}


def ng_link(seg, pos_vox):
    """A neuroglancer state that opens on this cell with the EM behind it."""
    state = {
        "layers": [
            {"type": "image", "source": f"precomputed://gs://h01-release/data/20210601/4nm_raw",
             "name": "EM"},
            {"type": "segmentation",
             "source": "precomputed://gs://h01-release/data/20210601/c3",
             "segments": [str(seg)], "name": "c3"},
        ],
        "navigation": {"pose": {"position": {
            "voxelSize": [8, 8, 33],
            "voxelCoordinates": [float(v) for v in pos_vox]}}, "zoomFactor": 8},
        "layout": "xy-3d",
    }
    return NG + urllib.parse.quote(json.dumps(state, separators=(",", ":")))


def main():
    import urllib.parse  # noqa: F401  (used via urllib.parse in ng_link)

    df = pd.read_csv(io.BytesIO(urllib.request.urlopen(
        f"{B}/c3/tables/somas.csv").read()))
    xyz_um = df[["x", "y", "z"]].to_numpy(float) * VOXEL_NM / 1000.0
    lo, hi = xyz_um.min(0), xyz_um.max(0)
    # A soma within 400 um of a side wall, or 30 um of the cut faces, has an
    # arbor that leaves the block. Those are bad representatives.
    inside = ((xyz_um > lo + [400, 400, 30]) & (xyz_um < hi - [400, 400, 30])).all(1)
    print(f"{inside.sum()} of {len(df)} somas sit comfortably inside the block")

    cv = CloudVolume(CLOUD, use_https=True, progress=False)
    rng = np.random.default_rng(3)
    out = []

    for cls in sorted(df.celltype.dropna().unique()):
        m = ((df.celltype == cls).to_numpy() & inside
             & df.c3_rep_manual.notna().to_numpy())
        idx = np.where(m)[0]
        if len(idx) == 0:
            print(f"{cls}: no candidate inside the block")
            continue
        pick = rng.choice(idx, size=min(CANDIDATES, len(idx)), replace=False)

        rows = []
        for j in pick:
            seg = int(df.c3_rep_manual.iloc[j])
            try:
                mesh = cv.mesh.get(seg, lod=LOD)[seg]
            except Exception as e:
                print(f"  {cls} {seg}: {type(e).__name__}")
                continue
            v = np.asarray(mesh.vertices) / 1000.0
            ext = v.max(0) - v.min(0)
            rows.append({
                "row": int(j), "seg": seg, "faces": int(len(mesh.faces)),
                "extent_um": [round(float(x), 1) for x in ext],
                "longest_um": float(ext.max()),
                "soma_vox": [int(df.x.iloc[j]), int(df.y.iloc[j]), int(df.z.iloc[j])],
                "soma_um": [round(float(x), 1) for x in xyz_um[j]],
                "layer": None if pd.isna(df.layer.iloc[j]) else df.layer.iloc[j],
            })
        if not rows:
            print(f"{cls}: no mesh loaded")
            continue

        L = np.array([r["longest_um"] for r in rows])
        med = float(np.median(L))
        order = np.argsort(np.abs(L - med))
        best = rows[int(order[0])]
        alts = [rows[int(i)] for i in order[1:3]]

        rec = {
            "class": cls, "label": LABEL.get(cls, cls),
            "population_in_block": int(m.sum()),
            "sampled": len(rows),
            "class_median_longest_um": round(med, 1),
            "spread_longest_um": [round(float(L.min()), 1), round(float(L.max()), 1)],
            "chosen": best,
            "alternates": alts,
            "neuroglancer": ng_link(best["seg"], best["soma_vox"]),
        }
        out.append(rec)
        print(f"{LABEL.get(cls, cls):26s} seg {best['seg']:>14d}  "
              f"longest {best['longest_um']:6.1f} um (class median {med:6.1f}, "
              f"sampled {len(rows)} of {m.sum()})")

    doc = {
        "about": "One representative cell per class in H01, chosen as the "
                 "candidate whose longest axis is closest to its class median "
                 "over a random sample. NOT PROOFREAD: these are c3 "
                 "agglomeration segments and may contain merge or split errors.",
        "segmentation": CLOUD,
        "mesh_lod": LOD,
        "selection": f"{CANDIDATES} candidates sampled per class from somas at "
                     f"least 400 um from the side walls and 30 um from the cut "
                     f"faces; the one closest to the class median longest axis "
                     f"was chosen.",
        "citation": "Shapson-Coe et al., Science 384, eadk4858 (2024)",
        "examples": out,
    }
    with open(os.path.join(ROOT, "data", "type-examples.json"), "w") as f:
        json.dump(doc, f, indent=1)

    # The handout.
    lines = [
        "# H01 cell type examples, proposed for proofreading",
        "",
        "One representative cell per class from the H01 human temporal cortex",
        "volume, intended for a public cell type gallery at",
        "https://amyleesterling.github.io/human-brain/",
        "",
        "**All of these are `c3` agglomeration segments and are not proofread.**",
        "Any of them may carry a merge or a split. They are the cells I would",
        "most like checked, because each one is about to stand for its whole",
        "class in front of a general audience.",
        "",
        f"Segmentation: `{CLOUD}`  ",
        "Reference: Shapson-Coe et al., Science 384, eadk4858 (2024)",
        "",
        "## How these were chosen",
        "",
        f"For each class, {CANDIDATES} cells were sampled at random from those",
        "whose soma sits at least 400 um from the side walls and 30 um from the",
        "cut faces, so the arbor is not truncated by the edge of the block. Each",
        "candidate's mesh was measured and the one whose longest axis is closest",
        "to that class's median was chosen, so none of these is an outlier.",
        "",
        "The sampled range column is worth a look on its own. A blood vessel",
        "cell sampled at 835 um and a spiny stellate at 1,302 um are not",
        "biology, they are almost certainly merges in the agglomeration. That",
        "spread is the reason this request exists: choosing the median protects",
        "the gallery from the obvious errors, but it cannot tell me whether the",
        "median cell itself is clean.",
        "",
        "## The cells",
        "",
        "| Class | c3 segment ID | Soma (8x8x33 nm voxels) | Layer | Longest axis | Sampled range | Cells in class |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in out:
        c = r["chosen"]
        lines.append(
            f"| {r['label']} | `{c['seg']}` | "
            f"{c['soma_vox'][0]}, {c['soma_vox'][1]}, {c['soma_vox'][2]} | "
            f"{c['layer'] or 'unclassified'} | {c['longest_um']:.0f} um | "
            f"{r['spread_longest_um'][0]:.0f} to {r['spread_longest_um'][1]:.0f} um | "
            f"{r['population_in_block']:,} |")
    lines += ["", "## Second and third choices", "",
              "If any cell above turns out to be badly merged, these are the next",
              "closest to the class median.", "",
              "| Class | Alternate segment IDs |", "|---|---|"]
    for r in out:
        alts = ", ".join(f"`{a['seg']}`" for a in r["alternates"])
        lines.append(f"| {r['label']} | {alts} |")
    lines += ["", "## Links", ""]
    for r in out:
        lines.append(f"- **{r['label']}** `{r['chosen']['seg']}`: "
                     f"[open in Neuroglancer]({r['neuroglancer']})")
    lines.append("")

    with open(os.path.join(ROOT, "PROOFREADING-REQUEST.md"), "w",
              encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"\nwrote data/type-examples.json and PROOFREADING-REQUEST.md "
          f"({len(out)} classes)")


if __name__ == "__main__":
    import urllib.parse
    main()
