"""The rest of the brain, for the tracts page.

Amy: the brain is missing a cerebellum. It is, and by construction. The glass
brain on that page is the HCP S1200 group average MIDTHICKNESS SURFACE, which
is the cerebral cortex and nothing else: no cerebellum, no brainstem, no deep
grey. Meanwhile the tractography includes a whole Cerebellum group and several
cranial nerves, so those bundles were drawn diving out of the bottom of the
brain into empty space.

WHAT THIS ADDS. The MNI152 brain mask, minus everything the cortical surface
already represents, turned into a surface. What is left is the cerebellum, the
brainstem and the deep grey: the parts of the brain that page was not drawing.

WHY SUBTRACT RATHER THAN JUST DRAW THE WHOLE MASK. Drawing the whole brain over
a surface that already covers the cerebrum gives two translucent shells in the
same place, which reads as fog. Subtracting is also the more honest object: it
is exactly the tissue the existing surface omits.

The subtraction is by distance to the cortical surface rather than by
containment, because the midthickness surface is not reliably watertight and
containment tests on open surfaces answer nonsense. Distance needs no such
assumption.

Writes meshes/cerebellum/rest.glb and data/cerebellum.json.
"""

import json
import os
import subprocess
import tempfile
import urllib.request

import numpy as np
import nibabel as nib
import trimesh
from scipy import ndimage
from skimage import measure
from scipy.spatial import cKDTree

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TPL = ("https://templateflow.s3.amazonaws.com/tpl-MNI152NLin2009cAsym/"
       "tpl-MNI152NLin2009cAsym_res-01_desc-brain_mask.nii.gz")

# How far from the cortical surface a voxel has to be before it counts as
# something that surface does not represent. The cortical ribbon is about 2.5 mm
# thick and the surface runs down its middle, so a few millimetres either side
# is still cortex. Ten is comfortably clear of it without eating the cerebellum,
# whose nearest point to the cortex is much further than that.
CLEAR_MM = 10.0


def p(*a):
    q = os.path.join(ROOT, *a)
    os.makedirs(os.path.dirname(q), exist_ok=True)
    return q


def decoded(glb):
    """Vertices as the browser sees them, past the Draco compression."""
    tmp = os.path.join(tempfile.mkdtemp(), "d.glb")
    subprocess.run(["npx", "--yes", "@gltf-transform/cli@latest", "cp", glb, tmp],
                   check=True, shell=True, capture_output=True)
    return trimesh.load(tmp, force="mesh", process=False)


def main():
    cache = p(".cache", "mni_brain_mask.nii.gz")
    if not os.path.exists(cache):
        print("fetching the MNI152 brain mask ...")
        urllib.request.urlretrieve(TPL, cache)
    img = nib.load(cache)
    mask = np.asarray(img.dataobj) > 0
    print(f"brain mask {mask.shape}, {int(mask.sum()):,} voxels")

    # The cortical surface this page already draws.
    cortex = trimesh.util.concatenate(
        [decoded(p("meshes", "cortex", h + ".glb")) for h in ("L", "R")])
    cv = np.asarray(cortex.vertices)
    print(f"cortical surface {len(cv):,} vertices, "
          f"z range {cv[:,2].min():.0f} to {cv[:,2].max():.0f} mm")

    ijk = np.array(np.nonzero(mask)).T
    xyz = nib.affines.apply_affine(img.affine, ijk)

    # SPACE CHECK, before anything is subtracted. The mask and the surface have
    # to be in the same millimetres or the subtraction removes the wrong half
    # of the brain and the result still looks like a plausible object.
    for ax, name in enumerate("xyz"):
        m0, m1 = xyz[:, ax].min(), xyz[:, ax].max()
        c0, c1 = cv[:, ax].min(), cv[:, ax].max()
        print(f"  {name}: mask {m0:7.1f} to {m1:6.1f}   cortex {c0:7.1f} to {c1:6.1f}")
        assert m0 - 12 <= c0 and c1 <= m1 + 12, (
            f"the cortical surface falls outside the brain mask on {name}, so "
            f"they are not in the same space")

    # Distance from every brain voxel to the nearest point of the cortical
    # surface. KD-tree, so this is seconds rather than the hours a containment
    # test would take, and it needs no watertightness.
    d = cKDTree(cv).query(xyz, workers=-1)[0]
    keep = d > CLEAR_MM
    print(f"\n  {keep.sum():,} of {len(xyz):,} brain voxels are more than "
          f"{CLEAR_MM:.0f} mm from the cortical surface")

    rest = np.zeros_like(mask)
    rest[tuple(ijk[keep].T)] = True
    # Close small holes and drop specks, then keep only the largest piece: the
    # cerebellum, brainstem and deep grey are one connected mass.
    rest = ndimage.binary_closing(rest, np.ones((3, 3, 3)), iterations=2)
    lab, n = ndimage.label(rest)
    sizes = ndimage.sum(rest, lab, range(1, n + 1))
    rest = lab == (int(np.argmax(sizes)) + 1)
    print(f"  {n} pieces, keeping the largest at {int(rest.sum()):,} voxels")

    sm = ndimage.gaussian_filter(rest.astype(np.float32), 1.2)
    verts, faces, _, _ = measure.marching_cubes(sm, level=0.5)
    verts = nib.affines.apply_affine(img.affine, verts)
    m = trimesh.Trimesh(vertices=verts, faces=faces, process=True)
    print(f"  marching cubes: {len(m.faces):,} faces, "
          f"watertight {m.is_watertight}")

    zmin_new, zmin_cortex = float(m.vertices[:, 2].min()), float(cv[:, 2].min())
    print(f"  reaches down to z {zmin_new:.0f} mm, against the cortex's "
          f"{zmin_cortex:.0f}")
    assert zmin_new < zmin_cortex - 5, (
        f"this does not extend below the cortical surface ({zmin_new:.0f} vs "
        f"{zmin_cortex:.0f}), so it adds nothing the page was missing")

    # THE CONTROL. The point of this mesh is to hold the bundles that had
    # nowhere to go. So the cerebellar bundles must now sit inside it, and the
    # association bundles, which run through the cerebrum, must not. One of
    # those alone proves nothing: a mesh the size of the whole head would pass
    # the first and fail the second.
    tr = json.load(open(p("data", "tracts.json"), encoding="utf-8"))
    solid = m.copy()
    solid.fill_holes()
    hits = {}
    for grp in ("Cerebellum", "Association"):
        mids = np.array([np.mean(b["mni_bounds"], axis=0)
                         for b in tr["bundles"] if b["group"] == grp])
        if not len(mids):
            continue
        inside = solid.contains(mids)
        hits[grp] = (int(inside.sum()), len(mids))
        print(f"  {grp:12s} {inside.sum():3d} of {len(mids):3d} bundle centres "
              f"inside ({100*inside.mean():.0f}%)")
    cb_in = hits["Cerebellum"][0] / hits["Cerebellum"][1]
    as_in = hits["Association"][0] / hits["Association"][1]
    assert cb_in > 0.6, (
        f"only {100*cb_in:.0f}% of cerebellar bundles land inside this mesh, so "
        f"it is not where the cerebellum is")
    assert as_in < 0.35, (
        f"{100*as_in:.0f}% of association bundles also land inside it, so it is "
        f"not selective and would just be a second brain-shaped blob")

    before = len(m.faces)
    if before > 90_000:
        try:
            m = m.simplify_quadric_decimation(face_count=90_000)
        except Exception:
            pass
    path = p("meshes", "cerebellum", "rest.glb")
    m.export(path)
    print(f"\n  {before:,} -> {len(m.faces):,} faces, "
          f"{os.path.getsize(path)/1e6:.2f} MB")

    doc = {
        "about": "The parts of the brain the HCP cortical surface does not "
                 "represent: cerebellum, brainstem and deep grey. Added "
                 "because the tractography includes cerebellar bundles and "
                 "cranial nerves, and those were being drawn diving out of the "
                 "bottom of a cortex-only glass brain into empty space.",
        "citation": "MNI152NLin2009cAsym brain mask, via TemplateFlow. "
                    "Fonov V, et al. Unbiased average age-appropriate atlases "
                    "for pediatric studies. NeuroImage 54, 313 (2011).",
        "licence": "CC BY 4.0",
        "source": TPL,
        "space": "MNI, the same millimetres as the tractography",
        "method": f"Brain mask minus every voxel within {CLEAR_MM:.0f} mm of "
                  f"the cortical surface, largest connected piece, marching "
                  f"cubes. Subtraction is by distance rather than containment "
                  f"because the midthickness surface is not reliably "
                  f"watertight and containment on an open surface answers "
                  f"nonsense.",
        "control": {
            "cerebellar_bundles_inside": f"{hits['Cerebellum'][0]} of "
                                         f"{hits['Cerebellum'][1]}",
            "association_bundles_inside": f"{hits['Association'][0]} of "
                                          f"{hits['Association'][1]}",
            "why_both": "One alone proves nothing. A mesh the size of the "
                        "whole head would contain every cerebellar bundle and "
                        "every association bundle too.",
        },
        "reaches_to_z_mm": round(zmin_new, 1),
        "cortex_reaches_to_z_mm": round(zmin_cortex, 1),
        "faces": int(len(m.faces)),
        "file": "meshes/cerebellum/rest.glb",
        "limits": "A template average, and a mask rather than an anatomical "
                  "segmentation: this is the shape of the tissue, not named "
                  "structures.",
    }
    with open(p("data", "cerebellum.json"), "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=1)
    print("wrote data/cerebellum.json")


if __name__ == "__main__":
    main()
