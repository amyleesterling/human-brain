"""Put the source estimates on a full resolution cortical surface.

The inverse solution lives on an ico-5 source space: 10,242 points per
hemisphere, which is the right density for solving an ill-posed problem and a
coarse thing to look at. fsaverage's actual surface is 163,842 vertices per
hemisphere, sixteen times as many.

WHAT THIS DOES, AND WHAT IT DOES NOT. It ships the full surface and, for every
one of its vertices, the index of the nearest source. The page then looks up
each vertex's value. That is nearest neighbour interpolation and nothing more:
no smoothing is invented, no value is created that the inverse did not produce,
and the patches are exactly as large as the source space's own resolution. The
picture gets a better surface, not better data, and the page says so.

Nearest is measured on the SPHERE, not in the folded brain. Two points can be
millimetres apart across a sulcus and far apart along the cortical sheet, and
the sphere is the surface on which cortical distance is what it should be.

Writes meshes/hires/{lh,rh}-{inflated,white}.glb and data/hires.json/.bin.
"""

import json
import os

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def p(*a):
    q = os.path.join(ROOT, *a)
    os.makedirs(os.path.dirname(q), exist_ok=True)
    return q


def main():
    import mne
    import nibabel as nib
    import trimesh
    from scipy.spatial import cKDTree
    from mne.datasets import fetch_fsaverage

    mne.set_log_level("WARNING")
    fs = fetch_fsaverage(verbose=False)
    surf_dir = os.path.join(fs, "surf")

    src = mne.read_source_spaces(
        os.path.join(fs, "bem", "fsaverage-ico-5-src.fif"), verbose=False)

    meshes, blob, layout = {}, b"", []
    off_total = 0
    for hi, (h, s) in enumerate(zip(("lh", "rh"), src)):
        used = s["vertno"]                      # 10,242 indices into the full surface
        sphere, _ = nib.freesurfer.read_geometry(os.path.join(surf_dir, f"{h}.sphere"))
        nfull = len(sphere)
        print(f"{h}: full surface {nfull:,} vertices, source space {len(used):,}")

        # Nearest source on the sphere, for every full-resolution vertex.
        tree = cKDTree(sphere[used])
        d, idx = tree.query(sphere, k=1)
        # The index is into this hemisphere's own source list, so the page adds
        # the hemisphere's offset itself.
        assert idx.max() < len(used)
        assert len(idx) == nfull
        # Every source must be somebody's nearest, or the source space and the
        # surface do not correspond and the lookup is meaningless.
        assert len(np.unique(idx)) == len(used), \
            f"{len(np.unique(idx))} of {len(used)} sources are reachable"
        print(f"   every source is the nearest of at least one vertex; "
              f"a vertex sits a median {np.median(d):.2f} sphere units from its source")

        for kind in ("inflated", "white"):
            v, f = nib.freesurfer.read_geometry(os.path.join(surf_dir, f"{h}.{kind}"))
            assert len(v) == nfull, f"{h}.{kind} has {len(v)} vertices, not {nfull}"
            out = p("meshes", "hires", f"{h}-{kind}.glb")
            trimesh.Trimesh(vertices=v, faces=f, process=False).export(out)
            meshes[f"{h}-{kind}"] = {
                "file": f"meshes/hires/{h}-{kind}.glb",
                "vertices": int(nfull), "faces": int(len(f)),
                "bytes": os.path.getsize(out),
            }
            print(f"   {kind:9s} {len(f):,} faces, "
                  f"{os.path.getsize(out)/1e6:.1f} MB")

        arr = idx.astype("<u2")
        layout.append({"hemi": h, "offset": len(blob), "count": int(nfull),
                       "source_offset": off_total, "sources": int(len(used))})
        blob += arr.tobytes()
        off_total += len(used)

    with open(p("data", "hires.bin"), "wb") as f:
        f.write(blob)
    with open(p("data", "hires.json"), "w") as f:
        json.dump({
            "about": "Full resolution fsaverage surfaces, and for every vertex "
                     "the index of its nearest source in the ico-5 source "
                     "space the inverse was solved on.",
            "interpolation": "nearest neighbour, measured on the spherical "
                             "surface so that distance means cortical distance "
                             "rather than distance through the skull. No "
                             "smoothing is applied and no value is invented: "
                             "the patches are the size of the source space's "
                             "own resolution.",
            "honesty": "This is a better surface, not better data. The inverse "
                       "solution still has 10,242 degrees of freedom per "
                       "hemisphere.",
            "head": "fsaverage (FreeSurfer). Check its terms before any "
                    "commercial or museum licence.",
            "vertices_per_hemisphere": meshes["lh-inflated"]["vertices"],
            "sources_per_hemisphere": layout[0]["sources"],
            "meshes": meshes,
            "bin": "data/hires.bin",
            "layout": layout,
        }, f, indent=1)
    tot = sum(m["bytes"] for m in meshes.values())
    print(f"\nhires.bin {os.path.getsize(p('data','hires.bin'))/1e6:.2f} MB, "
          f"meshes {tot/1e6:.1f} MB before compression")


if __name__ == "__main__":
    main()
