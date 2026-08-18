#!/usr/bin/env python3
"""
Flag points whose coordinates fall outside India's bounding box and write them
to data/out-of-india-points.csv for manual correction.

These are geocoding failures, not data errors: the facility is real and the
address is Indian, but the geocoder matched a same-named place abroad (most
land in the United States, which is why negative longitudes dominate) or
returned the null island at 0,0.

Nothing is dropped. Correct the coordinates, add a rule per facility to
data/manual-overrides.json, and re-run prep/build_all_india_rollups.py.

Run from the repo root.
"""
import csv, json

# Generous box: mainland + Andaman & Nicobar + Lakshadweep + Ladakh.
LAT_MIN, LAT_MAX = 6.0, 37.6
LNG_MIN, LNG_MAX = 68.0, 97.5

# A plain bounding box around India also swallows Sri Lanka, so a facility
# geocoded to Colombo passes it. Sri Lanka is the one neighbour that a rectangle
# separates cleanly -- no Indian territory sits in this box, since Rameswaram
# (9.28N, 79.31E) is west of it and Point Calimere (10.29N) is north of it.
#
# Nepal, Bhutan and Bangladesh CANNOT be excluded this way: any rectangle around
# them also covers Kolkata, Siliguri, Gorakhpur or the whole Northeast. Catching
# cross-border geocoding there needs a real India boundary polygon and a
# point-in-polygon test, which this script deliberately does not attempt.
# Format: (lat_min, lat_max, lng_min, lng_max).
NEIGHBOUR_BOXES = [
    (5.8, 10.0, 79.5, 82.1),   # Sri Lanka
]

# The resolved file is checked, not the raw layers, so a coordinate already
# corrected in manual-overrides.json stops being reported. Run this AFTER
# prep/build_all_india_rollups.py.
SOURCES = [
    "data/all-india-points.json",
    "data/infrastructure-cleaned.json",
]
OUT = "data/out-of-india-points.csv"

FIELDS = ["file", "name", "subtype", "source", "state", "city", "address",
          "latitude", "longitude", "reason",
          "corrected_latitude", "corrected_longitude", "notes"]


def in_neighbour(lat, lng):
    for la0, la1, ln0, ln1 in NEIGHBOUR_BOXES:
        if la0 <= lat <= la1 and ln0 <= lng <= ln1:
            return (la0, la1, ln0, ln1)
    return None


def reason(lat, lng):
    if in_neighbour(lat, lng):
        return "inside a neighbouring country - geocoded across the border"
    if lat == 0 and lng == 0:
        return "null island (0,0) - geocoder returned no match"
    if lng < 0:
        return "negative longitude - geocoded to the Americas"
    if not (LAT_MIN <= lat <= LAT_MAX):
        return "latitude outside India"
    return "longitude outside India"


def main():
    rows = []
    for path in SOURCES:
        try:
            points = json.load(open(path, encoding="utf-8"))
        except FileNotFoundError:
            continue
        for p in points:
            lat, lng = p.get("latitude"), p.get("longitude")
            if not isinstance(lat, (int, float)) or not isinstance(lng, (int, float)):
                continue
            inside = LAT_MIN <= lat <= LAT_MAX and LNG_MIN <= lng <= LNG_MAX
            if inside and not in_neighbour(lat, lng):
                continue
            rows.append({
                "file": path.split("/")[-1],
                "name": p.get("name", ""),
                "subtype": p.get("subtype", ""),
                "source": p.get("source", ""),
                "state": p.get("state", ""),
                "city": p.get("city", ""),
                "address": p.get("address", ""),
                "latitude": lat, "longitude": lng,
                "reason": reason(lat, lng),
                "corrected_latitude": "", "corrected_longitude": "", "notes": "",
            })

    rows.sort(key=lambda r: (str(r["state"] or ""), str(r["name"] or "")))
    with open(OUT, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)

    print(f"{len(rows)} points outside India -> {OUT}")
    from collections import Counter
    for k, v in Counter(r["subtype"] for r in rows).most_common():
        print(f"  {k:34} {v}")
    for k, v in Counter(r["reason"] for r in rows).most_common():
        print(f"  {k:60} {v}")


if __name__ == "__main__":
    main()
