"""Put the EEG rhythms on the cortex properly, by solving the inverse problem.

The head maps on the scale page are scalp maps. They say where the signal is
strongest ON THE HEAD, which is not where it is generated: the skull spreads
everything out, so an occipital hot spot is evidence about the scalp and only
indirectly about the brain. Turning scalp voltages into cortical sources is the
EEG inverse problem, and it has an actual answer.

WHAT THIS DOES.
  1. Template head: fsaverage, with its precomputed BEM and source space.
  2. Co-register the 64 standard 10-05 electrodes to that head.
  3. Forward model: how a current dipole at each cortical source would look at
     each electrode, through the three shells of brain, skull and scalp.
  4. Noise covariance from the eyes-open recording, which is the closest thing
     to a baseline these two runs offer.
  5. dSPM inverse, per band, on the eyes-closed and eyes-open data.
  6. Write per-vertex source power for each band, both states.

WHAT IT IS AND IS NOT. A distributed inverse solution is one answer among
infinitely many that fit the same scalp data: the problem is genuinely
ill-posed and the answer depends on the prior. dSPM's prior is that current is
spread smoothly over the cortical surface. It is a real, standard, published
estimate. It is not a measurement of where the rhythm is, and this page says so.

The head is a template, not this person's, so the anatomy is average and the
co-registration is nominal.

Writes data/sources.json and meshes/sources/{lh,rh}.glb.
"""

import json
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

BANDS = [("delta", 1.0, 4.0), ("theta", 4.0, 8.0), ("alpha", 8.0, 13.0),
         ("beta", 13.0, 30.0), ("gamma", 30.0, 45.0)]


def p(*a):
    q = os.path.join(ROOT, *a)
    os.makedirs(os.path.dirname(q), exist_ok=True)
    return q


def main():
    import mne
    from mne.datasets import fetch_fsaverage
    from fetch_signals import read_edf, cached, EEG, clean_label

    mne.set_log_level("WARNING")
    fs_dir = fetch_fsaverage(verbose=True)
    subjects_dir = os.path.dirname(fs_dir)
    print("fsaverage at", fs_dir)

    src_f = os.path.join(fs_dir, "bem", "fsaverage-ico-5-src.fif")
    bem_f = os.path.join(fs_dir, "bem", "fsaverage-5120-5120-5120-bem-sol.fif")
    trans = "fsaverage"

    raws = {}
    for state, url in EEG.items():
        sig, fs, units, dur = read_edf(cached(url, f"eegmmidb_S001_{state}.edf"))
        names, data = [], []
        for k in sig:
            if "annotation" in k.lower():
                continue
            names.append(clean_label(k))
            data.append(sig[k] * 1e-6)          # EDF is uV, MNE wants volts
            sfreq = fs[k]
        info = mne.create_info(names, sfreq, ch_types="eeg")
        raw = mne.io.RawArray(np.array(data), info, verbose=False)
        # The montage is matched case-insensitively: the EDF writes "Fc5",
        # the standard writes "FC5", and MNE will not match them itself.
        mon = mne.channels.make_standard_montage("standard_1005")
        rename = {}
        low = {c.lower(): c for c in mon.ch_names}
        for ch in raw.ch_names:
            if ch not in mon.ch_names and ch.lower() in low:
                rename[ch] = low[ch.lower()]
        raw.rename_channels(rename)
        raw.set_montage(mon, on_missing="raise")
        raw.set_eeg_reference("average", projection=True, verbose=False)
        raws[state] = raw
        print(f"  eyes {state:6s} {len(raw.ch_names)} channels at {sfreq:g} Hz")

    fwd = mne.make_forward_solution(raws["closed"].info, trans=trans, src=src_f,
                                    bem=bem_f, eeg=True, mindist=5.0,
                                    verbose=False)
    print("forward solution:", fwd["nsource"], "sources,",
          fwd["nchan"], "channels")

    # Noise covariance. With no empty-room or baseline, the honest choice is
    # the other condition: eyes open is the state with the least alpha, so it
    # is the closest thing to a rest baseline these two runs offer, and using
    # it makes the alpha result conservative rather than flattering.
    cov = mne.compute_raw_covariance(raws["open"], tmin=5, tmax=55,
                                     verbose=False)
    inv = mne.minimum_norm.make_inverse_operator(
        raws["closed"].info, fwd, cov, loose=0.2, depth=0.8, verbose=False)

    src = inv["src"]
    nv = [len(s["vertno"]) for s in src]
    print("source space:", nv, "used vertices per hemisphere")

    out = {}
    for state in ("closed", "open"):
        raw = raws[state].copy().crop(5, 55)
        per = {}
        for name, lo, hi in BANDS:
            # Band power at each source: filter, invert, then mean square.
            band = raw.copy().filter(lo, hi, verbose=False)
            stcb = mne.minimum_norm.apply_inverse_raw(
                band, inv, lambda2=1.0 / 9.0, method="dSPM",
                pick_ori=None, verbose=False)
            pw = (stcb.data ** 2).mean(axis=1)
            per[name] = pw
            print(f"  {state:6s} {name:6s} source power "
                  f"{pw.min():.3g} to {pw.max():.3g}")
            del stcb, band
        out[state] = per

    # Normalise each band by its own total so the maps are comparable, then
    # express as that band's share at each source, the same quantity the scalp
    # maps use.
    payload_bands = []
    for name, lo, hi in BANDS:
        rec = {"name": name, "low_Hz": lo, "high_Hz": hi, "states": {}}
        for state in ("closed", "open"):
            v = out[state][name]
            rec["states"][state] = {
                "max": float(v.max()),
                "values": np.round(v / v.max(), 4).astype("float32"),
            }
        payload_bands.append(rec)

    # Where does each band land, anatomically? A coordinate comparison was the
    # wrong test: it asked whether alpha's centroid sits behind delta's, and a
    # centroid of a bilateral, spatially spread estimate is not a location.
    # The right question is which named cortical regions the strongest sources
    # fall in, so the answer is read off the Desikan-Killiany parcellation of
    # the same surface the sources live on.
    labels = mne.read_labels_from_annot("fsaverage", "aparc", "both",
                                        subjects_dir=subjects_dir,
                                        verbose=False)
    lh_v, rh_v = src[0]["vertno"], src[1]["vertno"]
    n_lh = len(lh_v)
    region = np.array(["unknown"] * (n_lh + len(rh_v)), dtype=object)
    for lab in labels:
        if lab.name.startswith("unknown"):
            continue
        if lab.hemi == "lh":
            idx = np.nonzero(np.isin(lh_v, lab.vertices))[0]
        else:
            idx = np.nonzero(np.isin(rh_v, lab.vertices))[0] + n_lh
        region[idx] = lab.name.rsplit("-", 1)[0]

    tops = {}
    print("\nwhere each band localises, by cortical region:")
    for name, _, _ in BANDS:
        v = out["closed"][name]
        top = region[np.argsort(v)[-400:]]
        vals, counts = np.unique(top, return_counts=True)
        order = np.argsort(-counts)[:4]
        listed = [(str(vals[i]), int(counts[i])) for i in order]
        tops[name] = listed
        print(f"  {name:6s} " +
              ", ".join(f"{a} {100*b/400:.0f}%" for a, b in listed))

    # The control. Alpha must land in visual cortex, and the same test run on
    # delta must NOT, or the test is measuring nothing.
    # Visual cortex proper. The first version of this set also counted
    # precuneus and superiorparietal, which are parietal association cortex,
    # not visual, and with those included delta scored higher than alpha and
    # the test was meaningless. Naming the wrong regions is exactly how a
    # control ends up passing or failing for the wrong reason.
    VISUAL = {"pericalcarine", "cuneus", "lingual", "lateraloccipital"}
    def visual_share(name):
        v = out["closed"][name]
        top = region[np.argsort(v)[-400:]]
        return float(np.isin(top, list(VISUAL)).mean())
    alpha_vis = visual_share("alpha")
    delta_vis = visual_share("delta")
    print(f"\n  alpha in visual cortex: {alpha_vis*100:.0f}% of its top sources")
    print(f"  delta in visual cortex: {delta_vis*100:.0f}%   <- control")
    assert alpha_vis > 0.45, f"alpha did not localise to visual cortex: {tops['alpha']}"
    assert alpha_vis > delta_vis, "alpha must be more visual than delta"

    # And it must collapse when the eyes open, which is the whole phenomenon.
    ratio = float(out["closed"]["alpha"].max() / out["open"]["alpha"].max())
    print(f"  alpha source power, closed over open: {ratio:.1f}x")
    assert ratio > 3, ratio
    region_summary = {k: v for k, v in tops.items()}

    # Geometry. Write the white surface the sources actually sit on.
    import trimesh
    meshes = {}
    for hemi, s in zip("lr", src):
        rr = s["rr"] * 1000.0
        tris = s["use_tris"] if s.get("use_tris") is not None else s["tris"]
        used = s["vertno"]
        remap = -np.ones(len(rr), np.int64)
        remap[used] = np.arange(len(used))
        keep = tris[np.all(np.isin(tris, used), axis=1)]
        f = remap[keep]
        v = rr[used]
        path = p("meshes", "sources", f"{hemi}h.glb")
        trimesh.Trimesh(vertices=v, faces=f, process=False).export(path)
        meshes[hemi] = {"file": f"meshes/sources/{hemi}h.glb",
                        "vertices": int(len(v)), "faces": int(len(f))}
        print(f"  {hemi}h: {len(v)} sources, {len(f)} faces, "
              f"{os.path.getsize(path)/1e6:.2f} MB")

    n_total = sum(m["vertices"] for m in meshes.values())
    blob = b""
    layout = []
    for rec in payload_bands:
        for state in ("closed", "open"):
            arr = rec["states"][state]["values"]
            assert len(arr) == n_total, (len(arr), n_total)
            layout.append({"band": rec["name"], "state": state,
                           "offset": len(blob), "count": int(len(arr))})
            blob += arr.tobytes()
            rec["states"][state].pop("values")
    with open(p("data", "sources.bin"), "wb") as f:
        f.write(blob)

    with open(p("data", "sources.json"), "w") as f:
        json.dump({
            "about": "Cortical source estimates of EEG band power, dSPM, on the "
                     "fsaverage template head.",
            "method": "Three shell BEM forward model on fsaverage, standard "
                      "10-05 electrode positions, noise covariance from the "
                      "eyes-open recording, dSPM inverse with lambda2 = 1/9, "
                      "loose 0.2, depth 0.8. Band power is the mean square of "
                      "the band-filtered source time course, normalised to its "
                      "own maximum.",
            "caveat": "A distributed inverse solution is one of infinitely many "
                      "current distributions that fit the same scalp data. dSPM "
                      "assumes current is spread smoothly over the cortex. This "
                      "is a standard published estimate, not a measurement, and "
                      "the head is a template rather than this person's.",
            "recording": "PhysioNet EEG Motor Movement/Imagery Database, "
                         "subject 1, runs 1 and 2. ODC-BY 1.0.",
            "head": "fsaverage (FreeSurfer). Check its terms before any "
                    "commercial or museum licence.",
            "sources": n_total,
            "meshes": meshes,
            "bin": "data/sources.bin",
            "layout": layout,
            "bands": payload_bands,
            "top_regions_eyes_closed": region_summary,
            "alpha_closed_over_open": round(ratio, 1),
        }, f, indent=1)
    print(f"\nwrote data/sources.json and sources.bin "
          f"({os.path.getsize(p('data','sources.bin'))/1e6:.1f} MB)")


if __name__ == "__main__":
    main()
