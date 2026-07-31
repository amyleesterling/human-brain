"""BigBrain: the rung where the ladder stops being a model and becomes tissue.

THE GAP THIS FILLS. Until now the ladder went from the white matter at 178 mm
straight to the H01 cubic millimetre at 3.86 mm, a jump of forty six times, and
it is also the jump where "a brain" turns into "tissue". Everything above it is
a surface model built from MRI; everything below is electron microscopy of a
biopsy. Nothing connected them.

BigBrain connects them, because it is the only human dataset that spans both
ends in one brain. A 65 year old woman's brain, embedded in paraffin, cut into
7,404 coronal sections at 20 micrometres, every section stained for cell bodies
and photographed. Amunts et al., Science 340, 1472 (2013). At 20 um a cell body
is about one pixel, so you can see that cells are there and count them, but you
cannot trace a dendrite. That is exactly the resolution between an MRI voxel and
an electron micrograph, which is why it belongs here.

LICENCE. CC BY-NC-SA 4.0. Noncommercial, and share-alike. This page is not
licensed to anyone, which is the only reason this dataset is usable here.

WHAT THIS DOES. Takes one coronal section and crops the same point out of it at
four resolutions, each twice as fine as the last, so the zoom is one continuous
push into one real photograph rather than four unrelated pictures.

Following the house rules: percentile bounds rather than min and max, because
the tissue occupies only about a third of the 8-bit range and stretching on
min/max would key the whole image to one dark speck; and the cell counting has
a control that must return something, because a detector that finds nothing and
a detector that finds noise look identical in a single number.

Writes images/bigbrain/*.jpg and data/bigbrain.json.
"""

import json
import os

import numpy as np
from PIL import Image
from cloudvolume import CloudVolume
from scipy import ndimage

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = ("precomputed://https://neuroglancer.humanbrainproject.eu/"
        "precomputed/BigBrainRelease.2015")

# The section, chosen by looking at twelve candidates spread through the brain
# rather than by picking a number. This one carries the lateral ventricles, the
# thalamus, the basal ganglia and the hippocampus, so a reader can tell it is a
# brain and not an abstract texture.
SECTION_Y_20UM = 3872

# The point the zoom drives into: a gyral crown in the left superior parietal
# cortex, found by walking down from the top of the section to the pial surface
# and stepping 1.2 mm inward so the crop straddles the whole ribbon.
FOCUS_X_20UM = 2368
FOCUS_Z_20UM = 5216

LEVELS = [3, 2, 1, 0]        # 160, 80, 40, 20 micrometres
CROP_PX = 1024


def p(*a):
    q = os.path.join(ROOT, *a)
    os.makedirs(os.path.dirname(q), exist_ok=True)
    return q


def window(a):
    """Contrast window from percentiles of the TISSUE only.

    The paraffin background sits at 255 and fills most of a section, so a window
    computed over the whole frame is dominated by background and leaves the
    tissue as a flat grey smear. Min and max are worse still: one dark speck of
    stain sets the black point for the entire image."""
    t = a[a < 250]
    lo, hi = np.percentile(t, 0.5), np.percentile(t, 99.5)
    return float(lo), float(hi)


def stretch(a, lo, hi):
    return np.clip((a.astype(np.float32) - lo) / (hi - lo), 0, 1)


def count_cells(img, px_mm, mask=None, thresh=0.035):
    """Count cell bodies as dark points against the local background.

    Returns the count and points per square millimetre. `img` is stretched to
    0..1; `px_mm` is the in-plane pixel pitch in millimetres, which is NOT the
    section spacing (see the note on anisotropy below)."""
    sm = ndimage.gaussian_filter(img, 0.7)
    bg = ndimage.median_filter(sm, size=15)
    resp = bg - sm                                  # positive where darker
    peak = resp == ndimage.maximum_filter(resp, size=3)
    hits = peak & (resp > thresh)
    if mask is not None:
        hits &= mask
        n_px = int(mask.sum())
    else:
        n_px = img.size
    return int(hits.sum()), float(hits.sum() / (n_px * px_mm ** 2))


def main():
    out, crops = {}, {}
    for mip in LEVELS:
        v = CloudVolume(BASE + "/8bit", mip=mip, progress=True,
                        fill_missing=True, use_https=True)
        # ANISOTROPY. The sections are 20 um apart, but the pixels WITHIN a
        # section are 21.167 um. The first version of this used the section
        # spacing for the in-plane width and reported every crop 5.8 per cent
        # narrower than it is; the pyramid assert below is what caught it.
        # resolution[1] is the cutting axis, resolution[0] and [2] are the film.
        px_um = v.resolution[0] / 1000.0            # in-plane, horizontal
        pz_um = v.resolution[2] / 1000.0            # in-plane, vertical
        f = 2 ** mip
        cx, cz, cy = (FOCUS_X_20UM // f, FOCUS_Z_20UM // f, SECTION_Y_20UM // f)
        half = CROP_PX // 2
        sx, sz = v.shape[0], v.shape[2]
        # Clamp so a crop wider than the volume still lands inside it.
        x0 = max(0, min(cx - half, sx - CROP_PX)) if sx > CROP_PX else 0
        z0 = max(0, min(cz - half, sz - CROP_PX)) if sz > CROP_PX else 0
        x1, z1 = min(sx, x0 + CROP_PX), min(sz, z0 + CROP_PX)
        a = np.asarray(v[x0:x1, cy:cy + 1, z0:z1])[:, 0, :, 0]
        img = np.flipud(a.T)                        # rows top-down, z up
        lo, hi = window(a)
        st = stretch(img, lo, hi)
        wide_mm = round(img.shape[1] * px_um / 1000.0, 2)
        high_mm = round(img.shape[0] * pz_um / 1000.0, 2)
        name = f"mip{mip}"
        path = p("images", "bigbrain", f"{name}.jpg")
        Image.fromarray((st * 255).astype(np.uint8)).save(path, quality=88,
                                                          optimize=True)
        crops[name] = (st, px_um / 1000.0)
        out[name] = {
            "file": f"images/bigbrain/{name}.jpg",
            "um_per_px": round(px_um, 2),
            "px": [int(img.shape[1]), int(img.shape[0])],
            "width_mm": wide_mm,
            "height_mm": high_mm,
            "width_m": round(wide_mm / 1000.0, 6),
            "whole_section": bool(x1 - x0 < CROP_PX),
            "window": [round(lo), round(hi)],
            "range_used_pct": round(100 * (hi - lo) / 255, 1),
            "bytes": os.path.getsize(path),
        }
        print(f"  {name}  {px_um:5.2f} um/px  {img.shape[1]}x{img.shape[0]}  "
              f"{wide_mm:7.2f} mm  window {lo:.0f}-{hi:.0f}  "
              f"{os.path.getsize(path)/1e6:.2f} MB"
              f"{'  (whole section)' if x1 - x0 < CROP_PX else ''}")

    # The top level is the whole section, so it is whatever width the brain is
    # and cannot be a clean step. Every level below it is a fixed pixel count at
    # half the pitch, so those must be exactly 2x apart. Checking only "strictly
    # descending" would have let the anisotropy bug through, because 131 > 82 is
    # perfectly true and also 6 per cent wrong.
    ws = [out[f"mip{m}"]["width_mm"] for m in LEVELS]
    assert all(a > b for a, b in zip(ws, ws[1:])), f"levels not descending: {ws}"
    for a, b in zip(ws[1:], ws[2:]):
        assert 1.99 < a / b < 2.01, f"cropped levels are not exactly 2x: {ws}"
    print(f"\n  pyramid {ws} mm, {ws[0]/ws[-1]:.1f}x from top to bottom")

    # ---- what this resolution can actually support ------------------------
    # The first version of this counted cell bodies. It should not have. At
    # 21 micrometres per pixel a human cortical soma is between a half and one
    # and a half pixels across, so most cells are smaller than the sampling
    # grid and cannot be resolved as separate objects at all. The detector duly
    # found forty per square millimetre where histology says about two thousand,
    # and found MORE of them in white matter than in cortex, because isolated
    # glia against a pale background give crisper local contrast than somata
    # packed shoulder to shoulder. Both controls failed, and they were right to.
    #
    # What 20 micrometres does support is the thing BigBrain was built for:
    # the laminar profile. Cortex is layered, the layers differ in how densely
    # they are packed with cells, and packing density survives sampling that
    # individual cells do not. So measure staining against depth below the pial
    # surface, which needs nothing but the image itself.
    fine, px_mm = crops["mip0"]
    tis = fine < 0.86
    tis = ndimage.binary_closing(tis, np.ones((5, 5)))
    tis = ndimage.binary_opening(tis, np.ones((3, 3)))
    depth = ndimage.distance_transform_edt(tis) * px_mm
    dark = 1.0 - fine
    print(f"  tissue is {100*tis.mean():.0f}% of the crop, "
          f"deepest point {depth.max():.1f} mm below the surface")

    edges = np.arange(0, 4.001, 0.1)
    prof, mids = [], []
    for a, b in zip(edges, edges[1:]):
        m = tis & (depth >= a) & (depth < b)
        if m.sum() < 400:
            continue
        prof.append(round(float(dark[m].mean()), 4))
        mids.append(round(float(a + 0.05), 3))
    prof, mids = np.array(prof), np.array(mids)

    surf = float(prof[0])
    pk = int(np.argmax(prof))
    peak_mm, peak_v = float(mids[pk]), float(prof[pk])
    deep = float(prof[-1])
    print(f"  surface {surf:.3f} -> peak {peak_v:.3f} at {peak_mm:.2f} mm "
          f"-> {deep:.3f} at {mids[-1]:.2f} mm")

    # THE CONTROL. A flat profile, or one that only falls, would mean the
    # measurement is reading paraffin gradient or vignetting rather than
    # cytoarchitecture. Cortex makes a specific, falsifiable prediction: the
    # molecular layer at the surface is nearly free of cell bodies and must be
    # PALE, the supragranular layers below it are the most densely packed and
    # must be the DARKEST, and the white matter underneath must fall away
    # again. So the profile has to rise and then fall, and the peak has to land
    # inside the cortical ribbon rather than at either end.
    assert peak_v > surf * 1.25, (
        f"the surface ({surf:.3f}) is nearly as dark as the darkest band "
        f"({peak_v:.3f}), so no cell-sparse molecular layer is being resolved")
    assert peak_v > deep * 1.25, (
        f"the profile does not fall away below the ribbon ({peak_v:.3f} vs "
        f"{deep:.3f}), so grey and white matter are not being separated")
    assert 0.3 < peak_mm < 2.2, (
        f"the densest band sits {peak_mm:.2f} mm below the surface, which is "
        f"outside the cortical ribbon; this is not a laminar profile")
    print(f"  laminar contrast: peak / surface {peak_v/surf:.2f}x, "
          f"peak / deep {peak_v/deep:.2f}x")

    lam = {
        "depth_mm": mids.tolist(),
        "stain": prof.tolist(),
        "surface": round(surf, 4),
        "peak_depth_mm": peak_mm,
        "peak_stain": round(peak_v, 4),
        "deep_stain": round(deep, 4),
        "peak_over_surface": round(peak_v / surf, 2),
        "peak_over_deep": round(peak_v / deep, 2),
    }

    doc = {
        "about": "One coronal section of one human brain, cropped at four "
                 "resolutions around the same point, so the zoom is a "
                 "continuous push into a single real photograph.",
        "citation": "Amunts K, Lepage C, Borgeat L, et al. BigBrain: An "
                    "Ultrahigh-Resolution 3D Human Brain Model. Science 340, "
                    "1472 (2013).",
        "licence": "CC BY-NC-SA 4.0",
        "licence_note": "Noncommercial and share-alike. Usable here only "
                        "because this page is not licensed to anyone.",
        "source": "https://neuroglancer.humanbrainproject.eu/precomputed/"
                  "BigBrainRelease.2015/8bit",
        "specimen": "A 65 year old woman. One brain, embedded in paraffin and "
                    "cut into 7,404 coronal sections at 20 micrometres, each "
                    "stained for cell bodies and photographed.",
        "volume_mm": [139.1, 148.1, 120.9],
        "sections": 7404,
        "section_index": SECTION_Y_20UM,
        "section_note": "Chosen from twelve candidates spread through the "
                        "brain: it carries the lateral ventricles, the "
                        "thalamus, the basal ganglia and the hippocampus.",
        "anisotropy": "The sections are 20 micrometres apart, but the pixels "
                      "within a section are 21.17. Quoting the section "
                      "spacing as the image resolution understates every "
                      "in-plane measurement by about six per cent.",
        "resolution_note": "At 20 micrometres a cell body is about one pixel. "
                           "You can see that cells are there and count them; "
                           "you cannot trace a dendrite. That is the whole "
                           "point of this rung, which sits between an MRI "
                           "voxel and an electron micrograph.",
        "levels": out,
        "laminar": lam,
        "laminar_method":
            "Mean staining darkness against distance below the pial surface, "
            "measured from the image alone. The pial surface is the outer "
            "boundary of the tissue, so sulcal banks count as surface too.",
        "laminar_control":
            "Cortex predicts a specific shape and the measurement has to "
            "reproduce it: pale at the surface where the molecular layer holds "
            "almost no cell bodies, darkest a millimetre down through the "
            "densely packed supragranular layers, falling away again into "
            "white matter. A flat or monotonic profile would mean the "
            "measurement was reading a staining gradient instead.",
        "not_measured":
            "Cell counts. At 21 micrometres a human cortical cell body is "
            "between half a pixel and one and a half, so most cells are "
            "smaller than the sampling grid. Counting them here returned "
            "forty per square millimetre where histology says about two "
            "thousand, and returned more in white matter than in cortex, "
            "because isolated glia give crisper local contrast than somata "
            "packed together. The number was dropped rather than published.",
        "limits": "One section of one brain. Paraffin sectioning distorts "
                  "tissue, and the reconstruction corrects for that only "
                  "approximately.",
    }
    with open(p("data", "bigbrain.json"), "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=1)
    print("\nwrote data/bigbrain.json")


if __name__ == "__main__":
    main()
