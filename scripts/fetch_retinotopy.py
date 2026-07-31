"""Retinotopy: the map of visual space that is physically laid out on cortex.

Every point on the back of your cortex answers to one point in what you are
looking at, and neighbouring bits of cortex answer to neighbouring bits of the
world. That is not a metaphor. It is measurable in about an hour in a scanner,
and this is one person's.

SOURCE. OpenNeuro ds007283, NYU-NEI, CC0. Population receptive field fits from
prfvista, on that subject's own FreeSurfer surfaces.
  lh.angle  polar angle, radians, -pi to pi
  lh.eccen  eccentricity, degrees of visual angle from the centre of gaze
  lh.vexpl  variance explained by the pRF model, 0 to 1

WHAT IS MEASURED AND WHAT IS NOT. The angle and eccentricity are fits: the
scanner watched the cortex while a bar and a wedge swept the visual field, and
for each vertex the model asked which patch of visual space best explains that
vertex's time course. Where the model explains little, the fit means nothing,
so this ships the variance explained alongside and the page hides everything
below a threshold rather than colouring noise.

THE MAPS ARE REAL, AND CHECKED. A retinotopic map is smooth across the cortical
sheet: neighbouring vertices see neighbouring parts of the world. This script
measures that, and refuses to write anything unless it holds far better than
chance, with a shuffled control that must score about 1.

Writes data/retinotopy.json, data/retinotopy.bin, meshes/retino/*.glb.
"""

import json
import os
import urllib.request

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, ".cache", "retino")
S3 = "https://s3.amazonaws.com/openneuro.org/ds007283"
SUBJECT = "sub-wlsubj016"

# 488,106 faces per hemisphere is more than a page needs for a surface this
# smooth. A quarter of that still carries every fold of an inflated surface.
TARGET_FACES = 120_000
VEXPL_MIN = 0.10


def p(*a):
    q = os.path.join(ROOT, *a)
    os.makedirs(os.path.dirname(q), exist_ok=True)
    return q


def cached(url, name):
    os.makedirs(CACHE, exist_ok=True)
    dst = os.path.join(CACHE, name)
    if not os.path.exists(dst):
        print(f"  downloading {name}")
        urllib.request.urlretrieve(url, dst)
    return dst


def smoothness(vals, edges, gi, rng, circular=False):
    """Median change across a mesh edge, against median change between random
    pairs. Noise scores 1. A real map scores far below it."""
    def diff(a, b):
        d = vals[a] - vals[b]
        if circular:
            d = (d + np.pi) % (2 * np.pi) - np.pi
        return np.abs(d)
    near = float(np.median(diff(edges[:, 0], edges[:, 1])))
    far = float(np.median(diff(rng.choice(gi, len(edges)),
                               rng.choice(gi, len(edges)))))
    return near, far, near / far


def main():
    import nibabel as nib
    import trimesh

    rng = np.random.default_rng(0)
    hemis, report = {}, {}
    F_ANG, F_VEX = {}, {}
    blob = b""
    layout = []

    for h in ("lh", "rh"):
        surf = cached(f"{S3}/derivatives/freesurfer/{SUBJECT}/surf/{h}.inflated",
                      f"{h}.inflated")
        v, f = nib.freesurfer.read_geometry(surf)
        maps = {}
        for k in ("angle", "eccen", "vexpl"):
            g = cached(f"{S3}/derivatives/prfvista/{SUBJECT}/{h}.{k}.mgz",
                       f"{h}.{k}.mgz")
            a = np.asarray(nib.load(g).get_fdata()).squeeze()
            assert a.size == len(v), f"{h}.{k}: {a.size} values, {len(v)} vertices"
            maps[k] = a.astype(np.float64)
        print(f"{h}: {len(v):,} vertices, {len(f):,} faces")

        # --- the check, on the full resolution data ----------------------
        good = (maps["vexpl"] > VEXPL_MIN) & np.isfinite(maps["angle"]) \
            & np.isfinite(maps["eccen"])
        e = np.vstack([f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]])
        e = e[good[e[:, 0]] & good[e[:, 1]]]
        gi = np.where(good)[0]
        print(f"   {good.sum():,} vertices fit above {VEXPL_MIN:g} "
              f"variance explained, {len(e):,} edges between them")
        chk = {}
        for k, circ in (("eccen", False), ("angle", True)):
            near, far, ratio = smoothness(maps[k], e, gi, rng, circ)
            sh = maps[k].copy()
            sh[gi] = rng.permutation(sh[gi])
            _, _, rshuf = smoothness(sh, e, gi, rng, circ)
            chk[k] = {"neighbour": round(near, 4), "random": round(far, 4),
                      "ratio": round(ratio, 4), "shuffled_ratio": round(rshuf, 4)}
            print(f"   {k:6s} neighbours differ {near:7.3f}, random pairs "
                  f"{far:7.3f}, ratio {ratio:.3f}  (shuffled {rshuf:.3f})")
            assert ratio < 0.25, f"{h}.{k} is not smooth: {ratio}"
            assert 0.8 < rshuf < 1.25, f"{h}.{k} control is broken: {rshuf}"

        # --- decimate, then carry the maps across by nearest neighbour ----
        m = trimesh.Trimesh(vertices=v, faces=f, process=False)
        dec = m.simplify_quadric_decimation(face_count=TARGET_FACES)
        tree = __import__("scipy.spatial", fromlist=["cKDTree"]).cKDTree(v)
        d, idx = tree.query(np.asarray(dec.vertices), k=1)
        print(f"   decimated to {len(dec.vertices):,} vertices, "
              f"{len(dec.faces):,} faces; resampled maps moved a median "
              f"{np.median(d):.2f} mm")
        assert np.median(d) < 1.5, "decimation moved vertices too far"

        dmaps = {k: maps[k][idx] for k in maps}

        # --- the same check again, on what actually ships -----------------
        dgood = dmaps["vexpl"] > VEXPL_MIN
        de = np.vstack([dec.faces[:, [0, 1]], dec.faces[:, [1, 2]],
                        dec.faces[:, [2, 0]]])
        de = de[dgood[de[:, 0]] & dgood[de[:, 1]]]
        dgi = np.where(dgood)[0]
        for k, circ in (("eccen", False), ("angle", True)):
            _, _, ratio = smoothness(dmaps[k], de, dgi, rng, circ)
            chk[k]["ratio_after_decimation"] = round(ratio, 4)
            print(f"   {k:6s} after decimation, ratio {ratio:.3f}")
            assert ratio < 0.3, f"{h}.{k} lost its structure in decimation"

        out = p("meshes", "retino", f"{h}.glb")
        trimesh.Trimesh(vertices=np.asarray(dec.vertices),
                        faces=np.asarray(dec.faces), process=False).export(out)

        n = len(dec.vertices)
        # angle to uint16 over -pi..pi, eccen to uint16 over 0..40 degrees,
        # variance explained to uint8. Precision far finer than the fits.
        a16 = np.round((dmaps["angle"] + np.pi) / (2 * np.pi) * 65535
                       ).clip(0, 65535).astype("<u2")
        e16 = np.round(np.clip(dmaps["eccen"], 0, 40) / 40 * 65535
                       ).astype("<u2")
        v8 = np.round(np.clip(dmaps["vexpl"], 0, 1) * 255).astype("u1")
        F_ANG[h], F_VEX[h] = a16, v8
        for name, arr in (("angle", a16), ("eccen", e16), ("vexpl", v8)):
            layout.append({"hemi": h, "field": name, "offset": len(blob),
                           "count": int(n),
                           "dtype": "uint16" if arr.dtype == np.uint16 else "uint8"})
            blob += arr.tobytes()

        hemis[h] = {"file": f"meshes/retino/{h}.glb", "vertices": int(n),
                    "faces": int(len(dec.faces)),
                    "bytes": os.path.getsize(out)}
        report[h] = {"source_vertices": int(len(v)),
                     "fit_above_threshold": int(good.sum()),
                     "smoothness": chk}

    # --- the contralateral check --------------------------------------------
    # The oldest fact in visual neuroscience: each hemisphere sees the opposite
    # side of the world. It is also a free and decisive test of whether the
    # angle convention has been read correctly, because getting it wrong would
    # put both hemispheres on the same side. atan2 convention: 0 is the right
    # horizontal meridian, so the right visual field is |angle| < pi/2.
    contra = {}
    for h in ("lh", "rh"):
        a = np.asarray(F_ANG[h], np.float64) / 65535 * 2 * np.pi - np.pi
        v = np.asarray(F_VEX[h], np.float64) / 255
        row = {}
        for thr in (0.10, 0.25, 0.40):
            m = v > thr
            right = float(np.mean(np.abs(a[m]) < np.pi / 2))
            row[f"{thr:.2f}"] = {"n": int(m.sum()),
                                 "right_visual_field": round(100 * right, 1)}
        contra[h] = row
        print(f"  {h}: " + ", ".join(
            f"{k} -> {row[k]['right_visual_field']:.1f}% right" for k in row))

    # The control: shuffle which hemisphere each vertex belongs to and the
    # asymmetry has to vanish. If it does not, the test measures nothing.
    rng2 = np.random.default_rng(0)
    a_all = np.concatenate([np.asarray(F_ANG[h], np.float64) / 65535 * 2 * np.pi
                            - np.pi for h in ("lh", "rh")])
    v_all = np.concatenate([np.asarray(F_VEX[h], np.float64) / 255
                            for h in ("lh", "rh")])
    hemi = np.concatenate([np.full(len(F_ANG[h]), i)
                           for i, h in enumerate(("lh", "rh"))])
    m = v_all > 0.25
    sh = rng2.permutation(hemi[m])
    shuf = [round(100 * float(np.mean(np.abs(a_all[m][sh == i]) < np.pi / 2)), 1)
            for i in (0, 1)]
    print(f"  shuffled control: {shuf[0]}% and {shuf[1]}% right, must be near 50")
    assert contra["lh"]["0.25"]["right_visual_field"] > 85, contra
    assert contra["rh"]["0.25"]["right_visual_field"] < 15, contra
    assert all(40 < s < 60 for s in shuf), shuf
    contra["shuffled_control_pct_right"] = shuf

    with open(p("data", "retinotopy.bin"), "wb") as fh:
        fh.write(blob)

    with open(p("data", "retinotopy.json"), "w") as fh:
        json.dump({
            "about": "Population receptive field maps on one person's own "
                     "inflated cortical surface. Each vertex carries the polar "
                     "angle and eccentricity of the patch of visual space it "
                     "responds to, and how much of its time course the model "
                     "explains.",
            "source": f"{S3} ({SUBJECT}), OpenNeuro ds007283",
            "licence": "CC0",
            "attribution_note": "The dataset's own dataset_description.json "
                                "lists its authors as a TODO placeholder, so "
                                "there is no paper to cite and nobody named to "
                                "credit. It is CC0 and the credit is owed to "
                                "NYU CBI regardless.",
            "subject": SUBJECT,
            "vexpl_threshold": VEXPL_MIN,
            "angle_range_rad": [-np.pi, np.pi],
            "eccen_range_deg": [0, 40],
            "decimated_to_faces": TARGET_FACES,
            "resampling": "maps carried onto the decimated mesh by nearest "
                          "original vertex; the median move is printed on every "
                          "build and asserted under 1.5 mm",
            "check": report,
            "contralateral": contra,
            "meshes": hemis,
            "bin": "data/retinotopy.bin",
            "layout": layout,
        }, fh, indent=1)
    print(f"\nretinotopy.bin {os.path.getsize(p('data','retinotopy.bin'))/1e6:.2f} MB, "
          f"meshes {sum(h['bytes'] for h in hemis.values())/1e6:.2f} MB")


if __name__ == "__main__":
    main()
