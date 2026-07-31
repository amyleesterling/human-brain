"""The alpha rhythm as it actually moves, on the cortex.

The source page shows band POWER, which is a still: how strong the rhythm is at
each point, averaged over fifty seconds. A rhythm is not a still. This exports
the band-filtered source signal itself, frame by frame, so the page can play it.

WHAT IS REAL. The same inverse solution as the power map, applied to the same
recording, but keeping the time course instead of collapsing it to a mean
square. Every frame is a real instant of one real person's cortex, eyes closed
and eyes open, three seconds of each.

WHAT IS NOT. Alpha is 8 to 13 Hz, so three seconds contains about thirty
cycles. Played at real speed on a 60 Hz screen that is a flicker, so the page
slows it and says by how much. The signal is sampled at 30 frames per second,
which is above twice the band's top frequency and therefore loses nothing.

The values are signed: an oscillation swings both ways, and drawing only its
magnitude would turn one cycle into two.

Writes data/source-movie.json and .bin.
"""

import json
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

BAND = ("alpha", 8.0, 13.0)
SECONDS = 3.0
FPS = 30.0                     # above 2x the band's top frequency


def p(*a):
    q = os.path.join(ROOT, *a)
    os.makedirs(os.path.dirname(q), exist_ok=True)
    return q


def main():
    import mne
    from mne.datasets import fetch_fsaverage
    from fetch_signals import read_edf, cached, EEG, clean_label

    mne.set_log_level("WARNING")
    fs = fetch_fsaverage(verbose=False)
    src_f = os.path.join(fs, "bem", "fsaverage-ico-5-src.fif")
    bem_f = os.path.join(fs, "bem", "fsaverage-5120-5120-5120-bem-sol.fif")

    raws = {}
    for state, url in EEG.items():
        sig, fsr, units, dur = read_edf(cached(url, f"eegmmidb_S001_{state}.edf"))
        names, data = [], []
        for k in sig:
            if "annotation" in k.lower():
                continue
            names.append(clean_label(k))
            data.append(sig[k] * 1e-6)
            sfreq = fsr[k]
        info = mne.create_info(names, sfreq, ch_types="eeg")
        raw = mne.io.RawArray(np.array(data), info, verbose=False)
        mon = mne.channels.make_standard_montage("standard_1005")
        low = {c.lower(): c for c in mon.ch_names}
        raw.rename_channels({c: low[c.lower()] for c in raw.ch_names
                             if c not in mon.ch_names and c.lower() in low})
        raw.set_montage(mon, on_missing="raise")
        raw.set_eeg_reference("average", projection=True, verbose=False)
        raws[state] = raw

    fwd = mne.make_forward_solution(raws["closed"].info, trans="fsaverage",
                                    src=src_f, bem=bem_f, eeg=True,
                                    mindist=5.0, verbose=False)
    cov = mne.compute_raw_covariance(raws["open"], tmin=5, tmax=55, verbose=False)
    inv = mne.minimum_norm.make_inverse_operator(
        raws["closed"].info, fwd, cov, loose=0.2, depth=0.8, verbose=False)

    name, lo, hi = BAND
    blob, layout = b"", []
    peak = {}
    for state in ("closed", "open"):
        raw = raws[state].copy().crop(10, 10 + SECONDS + 1)
        band = raw.copy().filter(lo, hi, verbose=False)
        stc = mne.minimum_norm.apply_inverse_raw(
            band, inv, lambda2=1.0 / 9.0, method="dSPM", pick_ori="normal",
            verbose=False)
        # pick_ori="normal" keeps the sign, which an oscillation needs: drawing
        # only the magnitude would show two cycles for every real one.
        sf = raw.info["sfreq"]
        step = max(1, int(round(sf / FPS)))
        keep = np.arange(0, int(SECONDS * sf), step)
        d = stc.data[:, keep]
        print(f"  eyes {state:6s} {d.shape[0]:,} sources x {d.shape[1]} frames "
              f"at {sf/step:.1f} fps, {SECONDS:g} s")
        peak[state] = float(np.abs(d).max())
        layout.append({"state": state, "offset": len(blob),
                       "sources": int(d.shape[0]), "frames": int(d.shape[1]),
                       "scale": round(peak[state], 6)})
        blob += np.clip(np.round(d / peak[state] * 127), -127, 127) \
                  .astype(np.int8).tobytes()

    # Both states share one scale, so the collapse when the eyes open is
    # visible rather than normalised away.
    shared = max(peak.values())
    for L in layout:
        L["relative_amplitude"] = round(peak[L["state"]] / shared, 4)
    print(f"  eyes open reaches {peak['open']/peak['closed']*100:.1f}% of the "
          f"eyes closed amplitude")
    assert peak["closed"] > peak["open"] * 1.5, (peak, "alpha should collapse")

    with open(p("data", "source-movie.bin"), "wb") as f:
        f.write(blob)
    with open(p("data", "source-movie.json"), "w") as f:
        json.dump({
            "about": "The alpha rhythm as a time course on the cortex, from the "
                     "same inverse solution as the power maps.",
            "band": {"name": name, "low_Hz": lo, "high_Hz": hi},
            "seconds": SECONDS, "fps": FPS,
            "signed": True,
            "signed_note": "Values are signed because an oscillation swings "
                           "both ways. Drawing the magnitude would show two "
                           "cycles for every real one.",
            "recording": "PhysioNet EEG Motor Movement/Imagery Database, "
                         "subject 1, runs 1 and 2. ODC-BY 1.0.",
            "method": "dSPM with pick_ori normal, so the sign of the current "
                      "with respect to the cortical surface is kept.",
            "shared_scale": round(shared, 6),
            "bin": "data/source-movie.bin",
            "layout": layout,
        }, f, indent=1)
    print(f"\nwrote data/source-movie.bin "
          f"({os.path.getsize(p('data','source-movie.bin'))/1e6:.2f} MB)")


if __name__ == "__main__":
    main()
