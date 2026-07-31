"""Assemble the scale ladder: one push from a whole cortex to one synapse.

Every rung already exists in this repository. This does not fetch anything; it
measures what is on disk and writes the manifest the zoom is driven by, so the
scale readout on the page is the real size of the real object rather than a
caption someone typed.

WHY THE STAGES ARE SEPARATE SCENES. A whole cortex is 0.17 m and a synaptic
cleft is 2e-8 m. That is seven orders of magnitude, and float32 has about seven
significant digits, so a single scene holding both would lose the synapse to
rounding. Each stage is therefore drawn in its own units and the camera's field
of view is carried in metres alongside, which is what the readout prints. The
zoom is continuous; the arithmetic is not one coordinate system.

Writes data/ladder.json.
"""

import json
import os

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def p(*a):
    q = os.path.join(ROOT, *a)
    os.makedirs(os.path.dirname(q), exist_ok=True)
    return q


def mesh_extent_um(path):
    """Bounding box of a compressed mesh, in the units it was written in."""
    import subprocess, tempfile, trimesh
    tmp = os.path.join(tempfile.mkdtemp(), "d.glb")
    subprocess.run(["npx", "--yes", "@gltf-transform/cli@latest", "cp", path, tmp],
                   check=True, shell=True, capture_output=True)
    m = trimesh.load(tmp, force="mesh", process=False)
    v = np.asarray(m.vertices)
    return v.min(0), v.max(0), int(len(m.faces))


def main():
    soma = json.load(open(p("data", "somas.json"), encoding="utf-8"))
    cells = json.load(open(p("data", "cells.json"), encoding="utf-8"))
    syn = json.load(open(p("data", "synapse.json"), encoding="utf-8"))
    whole = json.load(open(p("data", "wholebrain.json"), encoding="utf-8"))
    surf = json.load(open(p("data", "surface.json"), encoding="utf-8"))
    tracts = json.load(open(p("data", "tracts.json"), encoding="utf-8"))

    # The hero cell: the biggest proofread pyramidal cell with a mesh, because
    # the rung above it is a whole cubic millimetre and the eye needs the jump
    # to land on something with reach.
    pyr = [c for c in cells["cells"]
           if c.get("klass") == "pyramidal" and c.get("mesh")]
    hero = max(pyr, key=lambda c: max(
        c["bounds_um"][1][i] - c["bounds_um"][0][i] for i in range(3)))
    hero_ext = [round(hero["bounds_um"][1][i] - hero["bounds_um"][0][i], 1)
                for i in range(3)]
    print(f"hero cell {hero['id']}: {hero['klass']}, {hero['layer']}, "
          f"{hero_ext} um, {hero['NSI']:,} incoming synapses")

    lo, hi = np.array(soma["bounds_um"])
    block_ext = (hi - lo)

    # Measure the top rungs rather than typing them. The first version put the
    # cortex at 0.17 m because that is roughly what a brain is, and the atlas
    # measured 0.151, so the ladder went backwards at the very top. The
    # ordering assert below caught it.
    cortex_mm = 0.0
    for h in ("L", "R"):
        _lo, _hi, _f = mesh_extent_um(p("meshes", "cortex", f"{h}.glb"))
        cortex_mm = max(cortex_mm, float(np.max(_hi - _lo)))
    tract_mm = 0.0
    for b in tracts["bundles"]:
        a, c = np.array(b["mni_bounds"])
        tract_mm = max(tract_mm, float(np.max(c - a)))
    print(f"measured: cortex {cortex_mm:.0f} mm, tracts {tract_mm:.0f} mm, "
          f"atlas brain {whole['longest_mm']:.0f} mm")

    STAGES = [
        {
            "id": "brain",
            "name": "A whole human brain",
            "fov_m": round(whole["longest_mm"] / 1000.0, 5),
            "note": "About a kilogram and a half, and the only organ that has "
                    "to be explained to itself. 283 named structures from the "
                    "Allen reference atlas.",
            "source": whole["citation"],
            "limits": whole["limits"],
            "kind": "wholebrain",
            "units_per_m": 1.0,
            "meshes": [
                {"file": whole["parts"]["shell"]["file"], "colour": "#8C9CB0",
                 "role": "shell", "opacity": 0.30},
                {"file": whole["parts"]["interior"]["file"], "colour": "#C98A5E",
                 "role": "interior", "opacity": 1.0},
            ],
        },
        {
            "id": "cortex",
            "name": "A whole human cortex",
            "fov_m": round(cortex_mm / 1000.0, 5),
            "note": "Just the folded sheet now, about 2 mm thick, and spread "
                    "flat roughly the area of a large dinner napkin. Two "
                    "thirds of it is buried inside the folds.",
            "source": surf["surface"]["citation"],
            "meshes": [{"file": "meshes/cortex/L.glb", "colour": "#6E8CA8"},
                       {"file": "meshes/cortex/R.glb", "colour": "#6E8CA8"}],
            "units_per_m": 1000.0,          # meshes are in millimetres
            "kind": "surface",
        },
        {
            "id": "tracts",
            "name": "The cable underneath it",
            "fov_m": round(tract_mm / 1000.0, 5),
            "note": "87 named bundles, averaged over 1,065 people. Everything "
                    "the cortex says to itself goes through here.",
            "source": tracts["citation"],
            "kind": "tracts",
            "units_per_m": 1000.0,
        },
        {
            "id": "block",
            "name": "One cubic millimetre",
            "fov_m": round(float(block_ext.max()) / 1e6, 6),
            "note": f"{soma['count']:,} cell bodies, every one of them where "
                    f"the microscope found it. This much tissue took 1.4 "
                    f"petabytes to photograph.",
            "source": soma["citation"],
            "kind": "block",
            "units_per_m": 1e6,             # micrometres
            "extent_um": [round(float(x), 1) for x in block_ext],
        },
        {
            "id": "cell",
            "name": "One neuron",
            "fov_m": round(max(hero_ext) / 1e6, 8),
            "note": f"A layer {hero['layer'][1:]} pyramidal cell, "
                    f"{hero['NSI']:,} synapses arriving on it, checked by hand.",
            "source": cells["citation"],
            "kind": "cell",
            "units_per_m": 1e6,
            "mesh": hero["mesh"],
            "extent_um": hero_ext,
            "segment": hero["id"],
            "stats": {k: hero[k] for k in ("NSI", "NSIe", "NSIi", "NSO", "Sp")},
        },
        {
            "id": "synapse",
            "name": "One synapse",
            "fov_m": round(max(syn["cube_um"]) / 1e6, 9),
            "note": "An axon ending, and the dendrite it is talking to. The gap "
                    "between them is about 20 nanometres wide.",
            "source": syn["citation"],
            "kind": "synapse",
            "units_per_m": 1e6,
            "meshes": [{"file": x["file"], "colour": x["colour"],
                        "role": x["role"], "volume_um3": x["volume_um3"]}
                       for x in syn["parts"]],
            "extent_um": syn["cube_um"],
        },
    ]

    for s in STAGES:
        print(f"  {s['id']:8s} field of view {s['fov_m']:.3e} m")

    # The rungs must not go backwards. The top three are genuinely the same
    # size, because a brain, its cortex and its cable all measure about 17 cm:
    # that part of the ladder is one scale showing different content, and the
    # page says so rather than faking a descent. Everything below must descend.
    fovs = [s["fov_m"] for s in STAGES]
    same = 3
    top = fovs[:same]
    assert max(top) / min(top) < 1.35, f"top rungs are not one scale: {top}"
    for s in STAGES[:same]:
        s["same_scale_group"] = "About 17 centimetres: one organ, three ways of "
        s["same_scale_group"] += "looking at it."
    rest = [max(top)] + fovs[same:]
    assert all(a > b for a, b in zip(rest, rest[1:])), rest
    span = fovs[0] / fovs[-1]
    print(f"\ntop to bottom: {span:,.0f} times, "
          f"{np.log10(span):.1f} orders of magnitude")

    doc = {
        "about": "One continuous push from a whole human cortex to a single "
                 "synapse, every rung a real measurement from this repository.",
        "why_separate_scenes":
            "A cortex is 0.17 m and a synaptic cleft is 2e-8 m. Float32 carries "
            "about seven significant digits, so one scene holding both would "
            "lose the synapse to rounding. Each stage is drawn in its own units "
            "with its true field of view carried in metres beside it.",
        "orders_of_magnitude": round(float(np.log10(span)), 2),
        "span": round(float(span)),
        "stages": STAGES,
    }
    with open(p("data", "ladder.json"), "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=1)
    print("wrote data/ladder.json")


if __name__ == "__main__":
    main()
