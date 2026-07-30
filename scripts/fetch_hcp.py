"""Pull the Human Connectome Project data this site's tract page is built on.

Three things, all openly downloadable with no account and no data use agreement:

  tracts    HCP1065 population-averaged tractography, 87 named white matter
            bundles from 1,065 HCP subjects. Yeh FC, Nat Commun 13, 4933
            (2022). CC-BY-SA 4.0. ICBM 2009a space.
  surface   The HCP S1200 group-average cortical surface, fs_LR 32k, MSMAll
            registered. 32,492 vertices per hemisphere.
  labels    What to colour that surface by: the Yeo 7 and 17 resting state
            networks, which are functional, the Glasser HCP-MMP1 360 region
            parcellation, and the group-average sulcal depth.

REGISTRATION. The two live in different spaces and are brought together with
the affine in the tractography's own file header, not by eye. Every .trk here
carries vox_to_ras

    [-1  0  0  78]
    [ 0 -1  0  76]
    [ 0  0  1 -50]

so a streamline point (x, y, z) in the file is (78 - x, 76 - y, z - 50) in MNI.
The check that this is right is anatomical and is asserted below: the left
corticospinal tract must run from the brainstem to the motor cortex on the left,
and the left arcuate must arch from frontal to temporal on the left. If the
affine were wrong those tests fail rather than the page quietly drawing a brain
inside out.

Usage:
  python scripts/fetch_hcp.py tracts
  python scripts/fetch_hcp.py surface
"""

import argparse
import gzip
import io
import json
import os
import struct
import urllib.request
import zipfile

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, ".cache")

TRK_URL = ("https://github.com/data-others/atlas/releases/download/hcp1065/"
           "hcp1065_avg_tracts_trk.zip")
HCPU = ("https://raw.githubusercontent.com/rmldj/hcp-utils/master/"
        "hcp_utils/data/")
DIED = ("https://raw.githubusercontent.com/DiedrichsenLab/fs_LR_32/master/")

# How much of each bundle to ship. The atlas has up to 34,156 streamlines in a
# single bundle and 9.2 million points in it; a page wants the shape of the
# tract, not every sample of it.
MAX_LINES = 220
POINTS_PER_LINE = 28


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


# --------------------------------------------------------------- tracts ----
def read_trk(raw):
    """TrackVis .trk: a 1000 byte header, then per streamline an int32 point
    count, that many (3 + n_scalars) float32, then n_properties float32."""
    assert raw[:5] == b"TRACK", raw[:8]
    n_scalars = struct.unpack_from("<h", raw, 36)[0]
    n_props = struct.unpack_from("<h", raw, 238)[0]
    v2r = np.frombuffer(raw, "<f4", 16, 440).reshape(4, 4).astype(np.float64)
    n_count = struct.unpack_from("<i", raw, 988)[0]
    stride = 3 + n_scalars
    off, lines = 1000, []
    while off < len(raw):
        m = struct.unpack_from("<i", raw, off)[0]
        off += 4
        pts = np.frombuffer(raw, "<f4", m * stride, off).reshape(m, stride)[:, :3]
        off += m * stride * 4 + n_props * 4
        lines.append(np.asarray(pts, np.float64))
    assert len(lines) == n_count, (len(lines), n_count)
    return lines, v2r


def resample(line, k):
    """Arc length resampling to exactly k points, so every streamline costs the
    same and a shader can walk them all with one index."""
    d = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(line, axis=0), axis=1))]
    if d[-1] <= 0:
        return np.repeat(line[:1], k, axis=0), 0.0
    t = np.linspace(0, d[-1], k)
    out = np.column_stack([np.interp(t, d, line[:, i]) for i in range(3)])
    return out, float(d[-1])


GROUP_LABEL = {
    "association": "Association", "projection": "Projection",
    "commissural": "Commissural", "cerebellum": "Cerebellum",
    "cranial nerve": "Cranial nerve",
}


def fetch_tracts():
    zpath = cached(TRK_URL, "hcp1065_avg_tracts_trk.zip")
    Z = zipfile.ZipFile(zpath)
    names = sorted(n for n in Z.namelist() if n.endswith(".trk.gz"))
    print(f"{len(names)} bundles")

    rng = np.random.default_rng(11)
    blobs, index = [], []
    offset = 0
    affine_seen = None

    for name in names:
        group, base = name.split("/")[0], name.split("/")[-1][: -len(".trk.gz")]
        lines, v2r = read_trk(gzip.decompress(Z.read(name)))
        if affine_seen is None:
            affine_seen = v2r
        else:
            assert np.allclose(affine_seen, v2r), f"{name} has a different affine"

        total = len(lines)
        # Sample without replacement, evenly, so a big bundle is thinned rather
        # than having its first streamlines taken.
        pick = (np.arange(total) if total <= MAX_LINES
                else rng.choice(total, MAX_LINES, replace=False))
        pick = np.sort(pick)

        res = np.empty((len(pick), POINTS_PER_LINE, 3), np.float64)
        lengths = np.empty(len(pick))
        for i, j in enumerate(pick):
            res[i], lengths[i] = resample(lines[j], POINTS_PER_LINE)

        # File coordinates to MNI, with the file's own affine.
        flat = res.reshape(-1, 3)
        mni = flat @ v2r[:3, :3].T + v2r[:3, 3]
        mni = mni.reshape(len(pick), POINTS_PER_LINE, 3)

        # All lengths over the WHOLE bundle, not just the shipped sample: this
        # is a real measurement of the atlas and it is what the page's transit
        # times are computed from, so it must not depend on the subsampling.
        all_len = np.array([
            float(np.linalg.norm(np.diff(l, axis=0), axis=1).sum()) for l in lines
        ])

        q = np.round(mni * 100).astype("<i2")   # 0.01 mm, well inside int16
        blobs.append(q.tobytes())

        index.append({
            "id": base,
            "group": GROUP_LABEL.get(group, group),
            "lines": int(len(pick)),
            "points_per_line": POINTS_PER_LINE,
            "offset": offset,
            "bytes": len(blobs[-1]),
            "streamlines_in_atlas": int(total),
            "length_mm": {
                "median": round(float(np.median(all_len)), 1),
                "p5": round(float(np.percentile(all_len, 5)), 1),
                "p95": round(float(np.percentile(all_len, 95)), 1),
            },
            "mni_bounds": [mni.reshape(-1, 3).min(0).round(1).tolist(),
                           mni.reshape(-1, 3).max(0).round(1).tolist()],
        })
        offset += len(blobs[-1])
        print(f"  {group:14s} {base:18s} {total:6d} -> {len(pick):4d} lines"
              f"   median {np.median(all_len):6.1f} mm", flush=True)

    with open(p("data", "tracts.bin"), "wb") as f:
        for b in blobs:
            f.write(b)

    # --- the anatomical checks -------------------------------------------
    def bounds(bid):
        return next(x for x in index if x["id"] == bid)["mni_bounds"]

    checks = []

    def check(label, ok, detail):
        checks.append({"check": label, "passed": bool(ok), "detail": detail})
        print(f"  [{'ok  ' if ok else 'FAIL'}] {label}: {detail}")
        return ok

    cst = bounds("CST_L")
    ok = check("left corticospinal tract is on the left",
               cst[1][0] < 5, f"max MNI x = {cst[1][0]}")
    ok &= check("left corticospinal tract runs brainstem to vertex",
                cst[0][2] < -30 and cst[1][2] > 50,
                f"MNI z from {cst[0][2]} to {cst[1][2]}")
    af = bounds("AF_L")
    ok &= check("left arcuate is on the left",
                af[1][0] < 5, f"max MNI x = {af[1][0]}")
    ok &= check("left arcuate spans frontal to posterior temporal",
                af[0][1] < -40 and af[1][1] > 20,
                f"MNI y from {af[0][1]} to {af[1][1]}")
    cc = bounds("CC")
    ok &= check("corpus callosum crosses the midline",
                cc[0][0] < -15 and cc[1][0] > 15,
                f"MNI x from {cc[0][0]} to {cc[1][0]}")
    if not ok:
        raise SystemExit("registration checks failed, refusing to write the index")

    meta = {
        "source": TRK_URL,
        "citation": "Yeh FC, Population-based tract-to-region connectome of the "
                    "human brain. Nat Commun 13, 4933 (2022).",
        "licence": "CC-BY-SA 4.0",
        "subjects": 1065,
        "space": "MNI, via the vox_to_ras affine in each .trk header",
        "affine": affine_seen.tolist(),
        "units": "millimetres, stored as int16 hundredths",
        "scale": 100,
        "bin": "data/tracts.bin",
        "registration_checks": checks,
        "sampling": f"at most {MAX_LINES} streamlines per bundle, each arc "
                    f"length resampled to {POINTS_PER_LINE} points. Lengths are "
                    f"measured on every streamline in the atlas, not on the "
                    f"shipped sample.",
        "bundles": index,
    }
    with open(p("data", "tracts.json"), "w") as f:
        json.dump(meta, f, indent=1)
    tot = sum(b["lines"] for b in index)
    print(f"\ntracts.bin {os.path.getsize(p('data','tracts.bin'))/1e6:.1f} MB, "
          f"{len(index)} bundles, {tot} streamlines, "
          f"{tot*POINTS_PER_LINE:,} points")


# -------------------------------------------------------------- surface ----
def fetch_surface():
    import nibabel as nib
    import trimesh

    surfaces, labels = {}, {}
    nvert = None
    for h in "LR":
        gs = cached(f"{HCPU}S1200.{h}.midthickness_MSMAll.32k_fs_LR.surf.gii",
                    f"S1200.{h}.midthickness.surf.gii")
        g = nib.load(gs)
        v = np.asarray(g.darrays[0].data, np.float64)
        f = np.asarray(g.darrays[1].data, np.int64)
        if nvert is None:
            nvert = len(v)
        # The control: labels come from a different repository than the
        # geometry, so vertex correspondence has to be asserted, not assumed.
        assert len(v) == nvert, f"{h} has {len(v)} vertices, expected {nvert}"
        surfaces[h] = (v, f)
        print(f"  {h}: {len(v)} vertices, {len(f)} faces, "
              f"MNI x {v[:,0].min():.0f} to {v[:,0].max():.0f}")

        out = p("meshes", "cortex", f"{h}.glb")
        trimesh.Trimesh(vertices=v, faces=f, process=False).export(out)
        print(f"     -> {out} ({os.path.getsize(out)/1e6:.1f} MB)")

    # What to colour it by. Yeo 7 and 17 are the resting state functional
    # networks; Glasser is the HCP's own 360 region parcellation.
    SETS = [
        ("yeo7", "Yeo_JNeurophysiol11_7Networks", "Resting state networks, 7"),
        ("yeo17", "Yeo_JNeurophysiol11_17Networks", "Resting state networks, 17"),
        ("glasser", "Glasser_2016", "HCP-MMP1, 360 regions"),
    ]
    packed, index = [], {}
    off = 0
    for key, stem, desc in SETS:
        per_hemi = []
        names = None
        for h in "LR":
            f = cached(f"{DIED}{stem}.32k.{h}.label.gii", f"{stem}.{h}.label.gii")
            g = nib.load(f)
            arr = np.asarray(g.darrays[0].data).astype(np.int32)
            assert len(arr) == nvert, f"{stem} {h}: {len(arr)} labels vs {nvert} vertices"
            lt = g.labeltable.get_labels_as_dict()
            per_hemi.append(arr)
            if names is None:
                names = lt
            else:
                names = {**names, **lt}
        arr = np.concatenate(per_hemi).astype("<u2")
        packed.append(arr.tobytes())
        index[key] = {
            "description": desc,
            "source": f"{DIED}{stem}.32k.[LR].label.gii",
            "offset": off, "count": int(len(arr)),
            "regions": {str(k): v for k, v in sorted(names.items())},
            "n_regions": int(len(set(arr.tolist()))),
        }
        off += len(packed[-1])
        print(f"  {key:9s} {index[key]['n_regions']:4d} distinct labels over "
              f"both hemispheres")

    with open(p("data", "surface-labels.bin"), "wb") as f:
        for b in packed:
            f.write(b)
    with open(p("data", "surface.json"), "w") as f:
        json.dump({
            "surface": {
                "source": f"{HCPU}S1200.[LR].midthickness_MSMAll.32k_fs_LR.surf.gii",
                "citation": "HCP S1200 group average, Van Essen et al., "
                            "NeuroImage 80:62 (2013). MSMAll registered.",
                "vertices_per_hemisphere": int(nvert),
                "mesh": {"L": "meshes/cortex/L.glb", "R": "meshes/cortex/R.glb"},
                "space": "MNI, same as the tractography",
            },
            "bin": "data/surface-labels.bin",
            "layout": "uint16 per vertex, left hemisphere then right, one block "
                      "per label set at its offset",
            "sets": index,
        }, f, indent=1)
    print(f"\nsurface-labels.bin "
          f"{os.path.getsize(p('data','surface-labels.bin'))/1e6:.2f} MB")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=["tracts", "surface"])
    a = ap.parse_args()
    {"tracts": fetch_tracts, "surface": fetch_surface}[a.what]()
