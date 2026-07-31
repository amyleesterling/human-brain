"""A whole human brain, for the top of the ladder.

The cortical surface this site already has is only the cortical sheet: no
cerebellum, no brainstem, no deep structures. The ladder should start with the
whole organ.

SOURCE. The HuBMAP Human Reference Atlas ships the Allen human reference atlas
as a ready made glTF: 283 named structures, CC BY 4.0, no account and no data
use agreement. Borner et al., Nature Methods (2025).

WHAT THIS DOES. Splits it into an outer shell, which is what the ladder's top
rung shows, and the named interior structures, which are what it dissolves into
on the way down. Both are decimated for the web.

Following the house rules: percentile bounds rather than min and max, because
stray vertices thousands of units from the rest silently destroy auto-framing;
and the before and after face totals are printed so a decimation that quietly
did nothing is visible.

Writes meshes/wholebrain/*.glb and data/wholebrain.json.
"""

import json
import os

import numpy as np
import trimesh

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, ".cache", "hubmap-brain.glb")

# The structures worth naming on the way down. Everything else is merged into
# the shell, because 283 separate meshes is a file list rather than a picture.
INTERIOR = [
    "thalamus", "caudate", "putamen", "globus_pallidus", "hippocamp",
    "amygdal", "cerebell", "brainstem", "pons", "medulla", "midbrain",
    "corpus_callosum", "ventricle", "substantia_nigra", "subthalamic",
    "accumbens", "hypothalamus", "claustrum",
]


def p(*a):
    q = os.path.join(ROOT, *a)
    os.makedirs(os.path.dirname(q), exist_ok=True)
    return q


def pct_extent(v):
    """Extent by percentile, not min and max. Meshes routinely carry a handful
    of vertices thousands of units from everything else, and a raw bounding box
    then collapses any auto-scale computed from it."""
    lo = np.percentile(v, 0.5, axis=0)
    hi = np.percentile(v, 99.5, axis=0)
    return lo, hi, hi - lo


def decimate(m, target):
    if len(m.faces) <= target:
        return m
    try:
        return m.simplify_quadric_decimation(face_count=target)
    except Exception:
        return m


def main():
    sc = trimesh.load(SRC)
    geoms = sc.geometry if hasattr(sc, "geometry") else {"mesh": sc}
    print(f"{len(geoms)} named meshes in the HuBMAP glTF")

    total_before = sum(len(g.faces) for g in geoms.values())
    allv = np.vstack([np.asarray(g.vertices) for g in geoms.values()])
    lo, hi, ext = pct_extent(allv)
    raw_ext = allv.max(0) - allv.min(0)
    print(f"  extent by percentile {np.round(ext, 1)}")
    print(f"  extent by min/max    {np.round(raw_ext, 1)}  "
          f"(ratio {np.round(raw_ext / ext, 2)})")

    inner_names, outer = [], []
    for name, g in geoms.items():
        low = name.lower()
        (inner_names if any(k in low for k in INTERIOR) else outer).append(name)
    print(f"  {len(inner_names)} interior structures, {len(outer)} merged into "
          f"the shell")

    parts = {}
    shell = trimesh.util.concatenate([geoms[n] for n in outer]) if outer else None
    if shell is not None:
        shell = decimate(shell, 160_000)
        path = p("meshes", "wholebrain", "shell.glb")
        shell.export(path)
        parts["shell"] = {"file": "meshes/wholebrain/shell.glb",
                          "faces": int(len(shell.faces)),
                          "structures": len(outer),
                          "bytes": os.path.getsize(path)}
        print(f"  shell    {len(shell.faces):8,} faces  "
              f"{os.path.getsize(path)/1e6:6.2f} MB")

    if inner_names:
        inner = trimesh.util.concatenate([geoms[n] for n in inner_names])
        inner = decimate(inner, 140_000)
        path = p("meshes", "wholebrain", "interior.glb")
        inner.export(path)
        parts["interior"] = {"file": "meshes/wholebrain/interior.glb",
                             "faces": int(len(inner.faces)),
                             "structures": len(inner_names),
                             "names": sorted(inner_names)[:40],
                             "bytes": os.path.getsize(path)}
        print(f"  interior {len(inner.faces):8,} faces  "
              f"{os.path.getsize(path)/1e6:6.2f} MB")

    total_after = sum(v["faces"] for v in parts.values())
    print(f"\n  faces {total_before:,} -> {total_after:,} "
          f"({100*total_after/total_before:.1f}% kept)")
    # A decimation that silently keeps almost everything is the failure mode
    # worth catching; so is one that deletes almost everything.
    assert 0.05 < total_after / total_before < 0.75, "decimation did not behave"

    # The atlas is in METRES, not millimetres. The first version of this script
    # assumed millimetres and the assertion below caught it: it reported a
    # brain 0.15 mm long. Guessing units is exactly the kind of silent error
    # that still renders and still looks plausible.
    longest_m = float(ext.max())
    longest_mm = longest_m * 1000.0
    print(f"  longest axis {longest_m:.4f} model units = {longest_mm:.0f} mm "
          f"if the file is in metres")
    assert 120 < longest_mm < 230, f"that is not a human brain: {longest_mm} mm"

    doc = {
        "about": "The whole human brain, from the HuBMAP Human Reference Atlas, "
                 "which packages the Allen human reference atlas as glTF.",
        "citation": "Borner K, et al. Human Reference Atlas. Nature Methods "
                    "(2025). Geometry derives from the Allen Human Reference "
                    "Atlas 3D, Ding et al.",
        "licence": "CC BY 4.0",
        "source": "https://raw.githubusercontent.com/hubmapconsortium/"
                  "ccf-releases/main/v2.0/models/3d-vh-f-allen-brain.glb",
        "units": "metres in the file; a human brain, so about 0.15 m long",
        "extent_mm": [round(float(x) * 1000, 1) for x in ext],
        "extent_method": "0.5 to 99.5 percentile, not min and max: a raw "
                         "bounding box is thrown off by the few stray vertices "
                         "these meshes carry.",
        "longest_mm": round(longest_mm, 1),
        "limits": "This is an atlas, an idealised average brain, not a person's. "
                  "It is also a surface model: the structures are boundaries, "
                  "not tissue.",
        "parts": parts,
    }
    with open(p("data", "wholebrain.json"), "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=1)
    print("wrote data/wholebrain.json")


if __name__ == "__main__":
    main()
