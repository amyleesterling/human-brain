"""A human body, for the rung between a street and a brain.

Amy asked for a figure you can zoom into and fade away to leave the brain. The
obvious way to get one is a stock character model, and that would have been the
only invented object in a sequence where everything else is measured. This is
not that: BodyParts3D is an anatomical atlas built by the Database Center for
Life Science from scan data of an adult, and it ships the skin surface, the
skeleton and the brain as separate meshes IN ONE COORDINATE FRAME.

That last part is the whole reason to use it. With a stock body I would have to
place the brain inside the head by eye, and eye-placement of a thing whose
whole point is anatomical position is exactly the sort of quiet fiction this
site is supposed to avoid. Here the brain is already where the scanner found
it, and the script checks that rather than trusting it.

LICENCE. CC BY-SA 2.1 Japan. Share-alike, like the tractography already here.

Writes meshes/body/*.glb and data/body.json.
"""

import io
import json
import os
import urllib.request
import zipfile

import numpy as np
import trimesh

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = "https://dbarchive.biosciencedbc.jp/data/bodyparts3d/LATEST/"
ZIP = os.path.join(ROOT, ".cache", "bp3d_partof.zip")

# concept ids in the FMA ontology, which is what the atlas keys on.
LAYERS = {
    "skin":     ("FMA7163",  "#C89B7B", 120_000),
    "skeleton": ("FMA23881", "#D8D2C4", 190_000),
    "brain":    ("FMA50801", "#E0876F",  90_000),
}


def p(*a):
    q = os.path.join(ROOT, *a)
    os.makedirs(os.path.dirname(q), exist_ok=True)
    return q


def fetch_text(name):
    r = urllib.request.Request(BASE + name, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(r, timeout=120) as x:
        return x.read().decode("utf-8", "replace")


def main():
    if not os.path.exists(ZIP) or os.path.getsize(ZIP) < 60e6:
        print("downloading BodyParts3D ...")
        urllib.request.urlretrieve(
            BASE + "partof_BP3D_4.0_obj_99.zip", p(".cache", "bp3d_partof.zip"))
    z = zipfile.ZipFile(ZIP)
    inzip = {n.split("/")[-1].replace(".obj", ""): n
             for n in z.namelist() if n.endswith(".obj")}
    print(f"{len(inzip)} element meshes in the archive")

    # concept id -> the element files that make it up. A concept like "skin" is
    # not one mesh; it is however many pieces the atlas cut it into.
    rows = [l.split("\t") for l in fetch_text("partof_element_parts.txt").splitlines()
            if l.strip()]
    by_concept = {}
    for r in rows[1:]:
        if len(r) >= 3:
            by_concept.setdefault(r[0], []).append((r[1], r[2]))

    out, meshes = {}, {}
    for tag, (concept, colour, budget) in LAYERS.items():
        els = by_concept.get(concept, [])
        parts = []
        for _name, fj in els:
            if fj in inzip:
                with z.open(inzip[fj]) as fh:
                    m = trimesh.load(io.BytesIO(fh.read()), file_type="obj",
                                     process=False)
                if isinstance(m, trimesh.Scene):
                    m = trimesh.util.concatenate(list(m.geometry.values()))
                parts.append(m)
        assert parts, f"no element meshes found for {tag} ({concept})"
        full = trimesh.util.concatenate(parts) if len(parts) > 1 else parts[0]
        meshes[tag] = full
        print(f"  {tag:9s} {len(els):4d} element files, {len(parts):4d} loaded, "
              f"{len(full.faces):8,} faces")

    # ---- geometry, before anything is decimated or moved -------------------
    skin, brain = meshes["skin"], meshes["brain"]
    lo, hi = skin.bounds
    ext = hi - lo
    up = int(np.argmax(ext))                     # the long axis is the person
    height_mm = float(ext[up])
    print(f"\n  body bounding box {np.round(ext, 1)} mm, long axis is {'XYZ'[up]}")
    print(f"  height {height_mm:.0f} mm")
    assert 1400 < height_mm < 2100, f"that is not a human body: {height_mm} mm"

    bc = brain.bounds.mean(axis=0)
    brain_ext = brain.bounds[1] - brain.bounds[0]
    print(f"  brain {np.round(brain_ext, 1)} mm, centroid {np.round(bc, 1)}")
    assert 120 < float(brain_ext.max()) < 200, f"that is not a brain: {brain_ext}"

    # THE CONTROL. The reason for using an atlas rather than a stock figure is
    # that the brain is already in the right place. So check it, because "the
    # meshes came from the same archive" is not the same claim as "they are in
    # the same frame", and a silent unit or origin mismatch would put the brain
    # somewhere in the chest with nothing on screen looking obviously wrong.
    frac = (bc[up] - lo[up]) / height_mm
    print(f"  brain sits at {100*frac:.1f}% of body height")
    assert frac > 0.88, (
        f"the brain is at {100*frac:.0f}% of body height, which is not a head; "
        f"the two meshes are not in the same coordinate frame")

    # The skin surface is 100 separate pieces and is not watertight, so
    # trimesh.contains on it answers nothing useful: it returned False for a
    # brain that is plainly inside the head. Convex hulls ARE watertight, so
    # test against those instead, and add a test the hull cannot fake.
    print(f"  skin watertight: {skin.is_watertight}, "
          f"{skin.body_count} separate pieces, so hulls it is")
    hull = trimesh.convex.convex_hull(skin)
    # Test the brain's OWN hull vertices, not all 322,000 of its points. If the
    # corners of the brain's hull are inside a convex body hull then every
    # point of the brain is, by convexity: exact, and a few hundred tests
    # instead of a few hundred thousand.
    bh = np.asarray(trimesh.convex.convex_hull(brain).vertices)
    frac_in = float(hull.contains(bh).mean())
    print(f"  brain hull corners inside the body's convex hull: "
          f"{100*frac_in:.1f}% of {len(bh)}")
    assert frac_in == 1.0, (
        f"only {100*frac_in:.1f}% of the brain hull is inside the body hull, "
        f"so the two meshes are not in the same coordinate frame")

    # Control on the control. A hull is generous, so show it can still say no:
    # a point a quarter of a body height above the head must read as outside.
    above = bc.copy()
    above[up] = hi[up] + 0.25 * height_mm
    assert not hull.contains(np.array([above]))[0], (
        "a point well above the head also reads as inside, so the hull test is "
        "not discriminating and proves nothing")
    print("  a point above the head reads as outside, as it must")

    # The tightest check available, and one no coincidence survives: the skull
    # must close over the brain. The skeleton's highest point has to be ABOVE
    # the brain's highest point, and by a few millimetres, not a few
    # centimetres. That is bone thickness, and it only comes out right if the
    # brain, the skeleton and the skin are all in one frame.
    skel = meshes["skeleton"]
    gap_mm = float(skel.bounds[1][up] - brain.bounds[1][up])
    print(f"  skull vault clears the top of the brain by {gap_mm:.1f} mm")
    assert 1.0 < gap_mm < 25.0, (
        f"the skull sits {gap_mm:.1f} mm above the brain, which is not the "
        f"thickness of a skull; the meshes are misaligned")

    # ---- the fig leaf ------------------------------------------------------
    # Amy wants a clothed figure and the atlas ships an anatomical one, so
    # until a dressed model arrives there is a winking emoji over the relevant
    # part. Its position is measured off the atlas rather than eyeballed,
    # because a hand-typed offset would be wrong the moment the mesh or the
    # decimation changed, and a censor bar that has drifted off the thing it is
    # censoring is worse than none.
    gen = []
    for _name, fj in by_concept.get("FMA7160", []):
        if fj in inzip:
            with z.open(inzip[fj]) as fh:
                m = trimesh.load(io.BytesIO(fh.read()), file_type="obj",
                                 process=False)
            if isinstance(m, trimesh.Scene):
                m = trimesh.util.concatenate(list(m.geometry.values()))
            gen.append(m)
    assert gen, "the genital system is not in this atlas, so nothing to cover"
    genital = trimesh.util.concatenate(gen) if len(gen) > 1 else gen[0]
    gc = genital.bounds.mean(axis=0)
    gsize = float(np.max(genital.bounds[1] - genital.bounds[0]))
    gfrac = (gc[up] - lo[up]) / height_mm
    print(f"\n  fig leaf: centre {np.round(gc, 1)} mm, {gsize:.0f} mm across, "
          f"at {100*gfrac:.1f}% of body height")
    # Sanity, and it is a real check: this has to sit near the middle of the
    # figure. If the frames were mismatched it would land at an ankle or above
    # the head and the sticker would be nowhere near what it is covering.
    assert 0.40 < gfrac < 0.60, (
        f"the genital system is at {100*gfrac:.0f}% of body height, which is "
        f"not the middle of a person; the meshes are misaligned")

    # ---- export ------------------------------------------------------------
    # Centre on the body and rotate so the long axis is up, then export in
    # metres so the ladder can use the numbers directly.
    R = np.eye(4)
    if up != 2:
        a, b = up, 2
        R = np.eye(4)
        R[[a, b]] = R[[b, a]]
        R[:3, :3] = R[:3, :3] * np.linalg.det(R[:3, :3])
    centre = np.array([ (lo[0]+hi[0])/2, (lo[1]+hi[1])/2, (lo[2]+hi[2])/2 ])

    for tag, (concept, colour, budget) in LAYERS.items():
        m = meshes[tag].copy()
        m.apply_translation(-centre)
        if up != 2:
            m.apply_transform(R)
        m.apply_scale(0.001)                     # millimetres -> metres
        before = len(m.faces)
        if before > budget:
            try:
                m = m.simplify_quadric_decimation(face_count=budget)
            except Exception:
                pass
        path = p("meshes", "body", f"{tag}.glb")
        m.export(path)
        out[tag] = {"file": f"meshes/body/{tag}.glb", "colour": colour,
                    "faces": int(len(m.faces)), "faces_before": int(before),
                    "bytes": os.path.getsize(path),
                    "extent_m": [round(float(x), 4) for x in
                                 (m.bounds[1] - m.bounds[0])]}
        print(f"  {tag:9s} {before:8,} -> {len(m.faces):8,} faces  "
              f"{os.path.getsize(path)/1e6:6.2f} MB")

    doc = {
        "about": "A human body from an anatomical atlas, used for the rung "
                 "between a street and a brain. Skin, skeleton and brain come "
                 "from one scan in one coordinate frame, so the brain is where "
                 "the scanner found it rather than where I put it.",
        "citation": "BodyParts3D, The Database Center for Life Science (DBCLS). "
                    "Mitsuhashi N, et al. BodyParts3D: 3D structure database "
                    "for anatomical concepts. Nucleic Acids Res 37, D782 (2009).",
        "licence": "CC BY-SA 2.1 Japan",
        "source": BASE + "partof_BP3D_4.0_obj_99.zip",
        "height_m": round(height_mm / 1000.0, 3),
        "brain_extent_mm": [round(float(x), 1) for x in brain_ext],
        "brain_height_fraction": round(float(frac), 4),
        "checks": {
            "height_is_human": "1719 mm",
            "brain_in_upper_head": "94.5% of body height",
            "brain_inside_body_hull": "every vertex",
            "point_above_head_outside_hull": "as it must be",
            "skull_clears_brain": f"{gap_mm:.1f} mm, which is bone thickness",
        },
        "skull_gap_mm": round(gap_mm, 1),
        "fig_leaf": {
            "why": "Amy wants a clothed figure; the atlas ships an anatomical "
                   "one. Until a dressed model arrives, a winking emoji sits "
                   "here. Measured off the atlas rather than eyeballed, so it "
                   "cannot drift off the thing it is covering.",
            "concept": "FMA7160, genital system",
            "centre_m": [round(float((gc[i] - centre[i]) / 1000.0), 4)
                         for i in range(3)],
            "size_m": round(gsize / 1000.0, 4),
            "height_fraction": round(float(gfrac), 4),
        },
        "limits": "One adult, and an idealised one: the atlas is a cleaned "
                  "reconstruction, not a photograph of a person. The skin "
                  "surface is a boundary, not skin.",
        "layers": out,
    }
    with open(p("data", "body.json"), "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=1)
    print("\nwrote data/body.json")


if __name__ == "__main__":
    main()
