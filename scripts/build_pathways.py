"""Turn the hand-written pathway chains into arithmetic on real tract lengths.

The chains are classical anatomy. The numbers are not: every leg's length is
that bundle's own measured median from the HCP1065 atlas, and the total is the
sum. Nothing is estimated and no leg exists that is not in the atlas.

It also adds the part people forget. Conduction along the cable is only half
the story: every relay costs a synapse, and a synapse is about a millisecond.
For the short pathways the synapses cost more than the wire does, which is
worth showing rather than hiding.
"""

import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SYNAPTIC_DELAY_MS = 1.0     # a chemical synapse, conservatively


def p(*a):
    q = os.path.join(ROOT, *a)
    os.makedirs(os.path.dirname(q), exist_ok=True)
    return q


src = json.load(open(p("data", "pathways-source.json"), encoding="utf-8"))
tracts = json.load(open(p("data", "tracts.json"), encoding="utf-8"))
by = {b["id"]: b for b in tracts["bundles"]}

# Every description has to name a bundle stem that actually exists, or it is a
# label for something the page cannot show.
stems = set()
for b in tracts["bundles"]:
    s = b["id"]
    for suf in ("_L", "_R"):
        if s.endswith(suf):
            s = s[: -len(suf)]
    stems.add(s)
unknown = [k for k in src["descriptions"] if k not in stems]
if unknown:
    raise SystemExit(f"descriptions for bundles that do not exist: {unknown}")
print(f"{len(src['descriptions'])} descriptions, all matching real bundles")
missing = sorted(stems - set(src["descriptions"]))
print(f"{len(missing)} bundle families still undescribed: {missing}")

VELOCITIES = [1, 10, 60, 120]
out = []
for act in src["actions"]:
    steps, total = [], 0.0
    for st in act["steps"]:
        b = by.get(st["tract"])
        if b is None:
            raise SystemExit(f"{act['id']}: no bundle {st['tract']}")
        L = b["length_mm"]["median"]
        total += L
        steps.append({
            "tract": st["tract"], "what": st["what"],
            "group": b["group"], "length_mm": L,
            "cumulative_mm": round(total, 1),
        })
    timing = {}
    for v in VELOCITIES:
        travel = total / (v * 1000.0) * 1000.0            # mm / (mm/s) -> ms
        syn = act["relays"] * SYNAPTIC_DELAY_MS
        timing[str(v)] = {
            "travel_ms": round(travel, 2),
            "synapses_ms": round(syn, 2),
            "total_ms": round(travel + syn, 2),
            "synapses_share_pct": round(100 * syn / (travel + syn), 0),
        }
    out.append({**{k: act[k] for k in ("id", "name", "blurb", "relays")},
                "steps": steps, "total_mm": round(total, 1), "timing": timing})
    t60 = timing["60"]
    print(f"  {act['name']:34s} {len(steps)} legs, {total:6.1f} mm, "
          f"at 60 m/s {t60['travel_ms']:5.2f} ms of travel plus "
          f"{t60['synapses_ms']:.0f} ms of synapses "
          f"({t60['synapses_share_pct']:.0f}% synapse)")

# The point worth making: at a realistic velocity the synapses dominate.
worst = max(out, key=lambda a: a["timing"]["60"]["synapses_share_pct"])
print(f"\nAt 60 m/s the synapses are the majority of the delay in "
      f"{sum(1 for a in out if a['timing']['60']['synapses_share_pct'] > 50)} "
      f"of {len(out)} pathways; the extreme is {worst['name']} at "
      f"{worst['timing']['60']['synapses_share_pct']:.0f}%.")

doc = {
    "about": src["about"],
    "caveat": src["caveat"],
    "synaptic_delay_ms": SYNAPTIC_DELAY_MS,
    "synaptic_delay_note": "A chemical synapse takes roughly a millisecond to "
                           "cross, so a pathway's delay is its cable time plus "
                           "one of these per relay. This is a standard figure, "
                           "not something measured here.",
    "citation": tracts["citation"],
    "descriptions": src["descriptions"],
    "actions": out,
}
with open(p("data", "pathways.json"), "w", encoding="utf-8") as f:
    json.dump(doc, f, indent=1, ensure_ascii=False)
print(f"\nwrote data/pathways.json ({os.path.getsize(p('data','pathways.json'))/1e3:.0f} kB)")
