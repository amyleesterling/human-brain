"""The rungs above the brain: a planet, a coastline, a city, a street.

Amy asked to start the zoom from space. The brain end of this ladder is all
real measured tissue, so the sky end has to be real measured imagery too, or
the picture stops being evidence halfway up. Everything here is public domain
government imagery: NASA's Blue Marble and Black Marble for the planet, NASA
GIBS for the satellite frames, and USGS NAIP for the one metre aerial over
Boston.

HOW THE FRAMES ARE BUILT. Not by picking a bounding box and reporting whatever
width it turned out to be. Each frame is specified by the width in metres it
should cover, and the bounding box is derived from that, so the scale readout
on the page is exact by construction rather than measured after the fact. The
metres-per-degree conversion uses the WGS84 ellipsoid at Boston's latitude,
because a degree of longitude at 42 north is 82 km, not 111.

THE CONTROL. Every frame has to contain Boston. A zoom whose frames do not nest
is not a zoom, it is five unrelated pictures, and nothing about the images
themselves would reveal that: each one would look like a perfectly good
photograph of somewhere.

Writes images/earth/*.jpg and data/earth.json.
"""

import json
import math
import os
import urllib.request

import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Boston Common, which is as good a centre for the city as any.
LAT, LON = 42.3551, -71.0657

GIBS = ("https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi?"
        "SERVICE=WMS&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image/jpeg&"
        "CRS=EPSG:4326&WIDTH={w}&HEIGHT={h}&LAYERS={lyr}&TIME={t}&BBOX={bbox}")
NAIP = ("https://imagery.nationalmap.gov/arcgis/rest/services/USGSNAIPPlus/"
        "ImageServer/exportImage?bbox={bbox}&bboxSR=4326&size={w},{h}&"
        "format=jpg&f=image")

# Each entry is the width the frame should cover, in metres.
FRAMES = [
    ("continent", 3_000_000, "gibs", "MODIS_Terra_CorrectedReflectance_TrueColor",
     "Eastern North America. Cloud cover is real weather on a real day, not a "
     "clean plate."),
    ("region",      400_000, "gibs", "MODIS_Terra_CorrectedReflectance_TrueColor",
     "New England, and the hook of Cape Cod."),
    ("metro",        24_000, "naip", None,
     "Boston: the harbour, the Charles, the grid of the Back Bay."),
    ("street",          420, "naip", None,
     "One metre per pixel. Individual buildings, individual trees, individual "
     "cars."),
]

PX = 1400


def p(*a):
    q = os.path.join(ROOT, *a)
    os.makedirs(os.path.dirname(q), exist_ok=True)
    return q


def m_per_deg(lat):
    """Metres per degree of latitude and of longitude on WGS84 at `lat`.

    A degree of longitude shrinks with the cosine of latitude: 111 km at the
    equator but 82 km at Boston. Using one number for both axes would stretch
    every frame east-west by a third and put the scale readout 35 per cent out."""
    r = math.radians(lat)
    mlat = 111132.92 - 559.82 * math.cos(2*r) + 1.175 * math.cos(4*r)
    mlon = 111412.84 * math.cos(r) - 93.5 * math.cos(3*r)
    return mlat, mlon


def bbox_for(width_m, lat, lon):
    """A square-on-the-ground box `width_m` across, centred on lat/lon."""
    mlat, mlon = m_per_deg(lat)
    dlon = width_m / mlon / 2.0
    dlat = width_m / mlat / 2.0
    return (lat - dlat, lon - dlon, lat + dlat, lon + dlon)


def fetch(url, path):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=120) as r:
        b = r.read()
    with open(path, "wb") as f:
        f.write(b)
    return len(b)


# Dates to try for the satellite frames. The first attempt used one fixed
# summer date and New England came back as a featureless white rectangle: total
# cloud. Nothing about the fetch failed, the file was a perfectly good JPEG of
# the top of a weather system. So try a spread of dates and choose by measuring
# cloud rather than by hoping.
CANDIDATE_DATES = ["2023-04-18", "2023-05-27", "2023-06-14", "2023-07-09",
                   "2023-08-15", "2023-09-12", "2023-10-08", "2023-10-24",
                   "2024-05-11", "2024-09-20"]


def cloudiness(path):
    """Fraction of the frame that is bright and colourless, which is cloud.

    Snow would fool this, which is why the candidate dates avoid winter."""
    im = Image.open(path).convert("RGB")
    a = np.asarray(im).astype(np.int16)
    lo = a.min(axis=2)
    hi = a.max(axis=2)
    return float(((lo > 165) & ((hi - lo) < 32)).mean())


def clearest_date(lyr, bbox):
    """Score each candidate date on a cheap thumbnail, return the clearest."""
    scored = []
    for d in CANDIDATE_DATES:
        tmp = p(".cache", f"probe_{lyr[:12]}_{d}.jpg")
        try:
            fetch(GIBS.format(w=256, h=256, lyr=lyr, t=d, bbox=bbox), tmp)
            scored.append((cloudiness(tmp), d))
        except Exception:
            continue
    assert scored, f"no candidate date fetched at all for {lyr}"
    scored.sort()
    return scored[0][1], scored[0][0], scored


def main():
    out = {}

    # ---- the planet -------------------------------------------------------
    # Equirectangular, so it must be exactly 2:1 or it will not wrap onto a
    # sphere without shearing the poles.
    for tag, lyr, t in (("earth_day", "BlueMarble_ShadedRelief_Bathymetry", "2023-08-15"),
                        ("earth_night", "VIIRS_CityLights_2012", "2012-01-01")):
        path = p("images", "earth", f"{tag}.jpg")
        n = fetch(GIBS.format(w=4096, h=2048, lyr=lyr, t=t,
                              bbox="-90,-180,90,180"), path)
        im = Image.open(path)
        assert im.size == (4096, 2048), f"{tag} came back {im.size}"
        assert im.size[0] == 2 * im.size[1], "not equirectangular"
        out[tag] = {"file": f"images/earth/{tag}.jpg", "px": list(im.size),
                    "layer": lyr, "bytes": n,
                    "projection": "equirectangular, plate carree"}
        print(f"  {tag:12s} {im.size[0]}x{im.size[1]}  {n/1e6:5.2f} MB  {lyr}")

    EARTH_D = 12_742_000
    out["earth"] = {
        "width_m": EARTH_D, "name": "Earth",
        "note": "12,742 kilometres across. The night side is real: VIIRS "
                "measured the light cities throw away upward.",
    }

    # ---- the frames -------------------------------------------------------
    prev = EARTH_D
    for name, width_m, api, lyr, note in FRAMES:
        south, west, north, east = bbox_for(width_m, LAT, LON)
        path = p("images", "earth", f"{name}.jpg")
        bb = f"{south},{west},{north},{east}"
        chosen, cloud = None, None
        if api == "gibs":
            chosen, cloud, scored = clearest_date(lyr, bb)
            print(f"  {name:12s} dates tried: " + ", ".join(
                f"{d} {100*c:.0f}%" for c, d in scored[:4]) + " ...")
            url = GIBS.format(w=PX, h=PX, lyr=lyr, t=chosen, bbox=bb)
        else:
            url = NAIP.format(bbox=f"{west},{south},{east},{north}", w=PX, h=PX)
        n = fetch(url, path)
        im = Image.open(path)
        assert im.size == (PX, PX), f"{name} came back {im.size}, not {PX}"
        cloud = cloudiness(path)
        # A frame that is more than half cloud shows weather, not geography.
        assert cloud < 0.5, (
            f"{name} is {100*cloud:.0f}% cloud even on the clearest candidate "
            f"date; it shows a weather system rather than the ground")

        # THE CONTROL. The frame must contain Boston, and must be strictly
        # inside the frame above it. Five pictures that do not nest still look
        # like five good pictures.
        assert south < LAT < north and west < LON < east, (
            f"{name} does not contain Boston: {(south, west, north, east)}")
        assert width_m < prev, f"{name} is not smaller than the frame above it"

        m_px = width_m / PX
        out[name] = {
            "file": f"images/earth/{name}.jpg",
            "width_m": width_m,
            "m_per_px": round(m_px, 3),
            "bbox": [round(x, 5) for x in (south, west, north, east)],
            "px": list(im.size),
            "source": "NASA GIBS" if api == "gibs" else "USGS NAIP",
            "layer": lyr,
            "date": chosen,
            "cloud_fraction": round(cloud, 3),
            "note": note,
            "bytes": n,
        }
        print(f"  {name:12s} {width_m:>9,} m across  {m_px:8.2f} m/px  "
              f"{n/1e6:5.2f} MB  cloud {100*cloud:4.0f}%  "
              f"{chosen or 'USGS NAIP'}")
        prev = width_m

    # A sanity check on the conversion itself: at Boston's latitude a degree of
    # longitude must be about 82 km, and clearly less than a degree of latitude.
    mlat, mlon = m_per_deg(LAT)
    print(f"\n  at {LAT} N: 1 deg lat = {mlat:,.0f} m, 1 deg lon = {mlon:,.0f} m")
    assert 82_000 < mlon < 83_000, f"longitude scale is wrong: {mlon}"
    assert mlon < mlat, "longitude degrees must be shorter than latitude ones here"

    steps = [EARTH_D] + [f[1] for f in FRAMES]
    print("  descent: " + "  ".join(f"{a/b:.0f}x" for a, b in zip(steps, steps[1:])))

    doc = {
        "about": "The rungs above the brain, from a planet down to a street in "
                 "Boston. All public domain government imagery.",
        "centre": {"lat": LAT, "lon": LON, "place": "Boston Common"},
        "citation": "Blue Marble and city lights: NASA Earth Observatory / "
                    "NASA Worldview (GIBS). Satellite frames: NASA GIBS, "
                    "MODIS on Terra. Aerial: USGS National Agriculture Imagery "
                    "Program, 1 m.",
        "licence": "Public domain (NASA and USGS)",
        "method": "Each frame is specified by the width in metres it should "
                  "cover; the bounding box is derived from that using the "
                  "WGS84 metres-per-degree at this latitude. The scale readout "
                  "is therefore exact by construction.",
        "control": "Every frame is checked to contain Boston and to be "
                   "strictly smaller than the one above it. Frames that do not "
                   "nest would still each look like a good photograph.",
        "limits": "The satellite frames are single days with real weather. The "
                  "aerial imagery is a different day again, and the night "
                  "lights are a 2012 composite, so this is not one instant.",
        "frames": out,
    }
    with open(p("data", "earth.json"), "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=1)
    print("wrote data/earth.json")


if __name__ == "__main__":
    main()
