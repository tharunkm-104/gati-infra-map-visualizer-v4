#!/usr/bin/env python3
"""
Roll the all-India point layers up into the tables the dashboard reads.

Inputs   data/all-india-health-points.json    (prep/build_all_india_health.py)
         data/all-india-language-points.json  (prep/build_all_india_language.py)
         data/manual-overrides.json           (hand-edited; optional)

Outputs  data/all-india-points.json           BOTH layers merged, overrides applied
         data/all-india-states.json           one row per state/UT
         data/all-india-cities.json           one row per (state, city)
         data/all-india-coverage.json         how much of the layer is city-attributed

The dashboard reads all-india-points.json, NOT the two raw *-points.json files.
That is the whole reason this step exists: manual corrections have to reach the
map, not just the tables. The raw files stay as the untouched output of the
source builders so a correction is always visible as a diff against them.

RUN ORDER
  1. prep/build_all_india_health.py
  2. prep/build_all_india_language.py
  3. prep/build_all_india_rollups.py      <- this file, always last

CITY COVERAGE
Not every point carries a usable city. NABH cities are parsed out of free-text
postal addresses, so a share of them come back blank; those points still render
on the map and still count at state level, but they cannot be attributed to a
city row. data/all-india-coverage.json records exactly how many, per layer, so
the dashboard can state its own gaps instead of silently under-reporting.
"""
import json, os
from collections import defaultdict

HEALTH = "data/all-india-health-points.json"
LANGUAGE = "data/all-india-language-points.json"
OVERRIDES = "data/manual-overrides.json"
OUT_POINTS = "data/all-india-points.json"
OUT_STATES = "data/all-india-states.json"
OUT_CITIES = "data/all-india-cities.json"
OUT_COVERAGE = "data/all-india-coverage.json"

# subtype -> count column. Must stay in step with ALL_INDIA_SUBTYPE_KEY in app.js.
SUBTYPE_KEY = {
    "Goethe/PASCH/Zentrum School": "goethe_schools",
    "Goethe/TELC Exam Centre": "exam_centres",
    "HEI Offering German": "heis_german",
    "PDOT Centre": "pdot_siics",
    "SIIC Centre": "pdot_siics",
    "IISC Centre (PMKK)": "iiscs",
    "NABH Accredited Health Facility": "nabh_facilities",
    "NMC Medical College": "nmc_colleges",
    "INC Nursing College": "inc_colleges",
}
COUNT_KEYS = ["goethe_schools", "exam_centres", "heis_german", "pdot_siics", "iiscs",
              "nabh_facilities", "nmc_colleges", "inc_colleges"]

# Same city under two spellings collapses to one row. Extend freely.
CITY_NORM = {
    "bangalore": "Bengaluru", "bengaluru": "Bengaluru",
    "bombay": "Mumbai", "mumbai": "Mumbai",
    "calcutta": "Kolkata", "kolkata": "Kolkata",
    "madras": "Chennai", "chennai": "Chennai",
    "cochin": "Kochi", "ernakulam": "Kochi", "kochi": "Kochi",
    "trivandrum": "Thiruvananthapuram", "thiruvananthapuram": "Thiruvananthapuram",
    "calicut": "Kozhikode", "kozhikode": "Kozhikode",
    "gurgaon": "Gurugram", "gurugram": "Gurugram",
    "pondicherry": "Puducherry", "puducherry": "Puducherry",
    "prayagraj": "Prayagraj", "allahabad": "Prayagraj",
    "vizag": "Visakhapatnam", "visakhapatnam": "Visakhapatnam",
    "new delhi": "New Delhi", "delhi": "New Delhi",
    "secunderabad": "Hyderabad", "hyderabad": "Hyderabad",
    "navi mumbai": "Navi Mumbai", "thane": "Thane",
    "mysore": "Mysuru", "mysuru": "Mysuru",
}


def norm_city(c):
    c = " ".join((c or "").strip().split())
    if not c:
        return ""
    return CITY_NORM.get(c.lower(), c.title() if c.islower() or c.isupper() else c)


def load(path):
    if not os.path.exists(path):
        print(f"  (missing, skipped) {path}")
        return []
    return json.load(open(path, encoding="utf-8"))


def apply_overrides(points):
    """Hand corrections from data/manual-overrides.json.

    Each entry matches on `match` (any subset of point fields, compared
    case-insensitively as strings) and either sets fields via `set`, or drops
    the point with `"drop": true`. First matching rule wins per point.
    """
    if not os.path.exists(OVERRIDES):
        return points, 0, 0
    rules = [r for r in json.load(open(OVERRIDES, encoding="utf-8")).get("overrides", [])
             if not r.get("_disabled")]
    if not rules:
        return points, 0, 0

    def matches(p, crit):
        return all(str(p.get(k, "")).strip().lower() == str(v).strip().lower()
                   for k, v in crit.items())

    kept, edited, dropped = [], 0, 0
    for p in points:
        rule = next((r for r in rules if matches(p, r.get("match", {}))), None)
        if rule is None:
            kept.append(p)
            continue
        if rule.get("drop"):
            dropped += 1
            continue
        p.update(rule.get("set", {}))
        p["manuallyEdited"] = True
        edited += 1
        kept.append(p)
    return kept, edited, dropped


def blank_row(extra):
    row = {k: 0 for k in COUNT_KEYS}
    row.update({"government": 0, "private": 0, "not_specified": 0,
                "lat_sum": 0.0, "lng_sum": 0.0, "n": 0})
    row.update(extra)
    return row


def tally(row, p):
    key = SUBTYPE_KEY.get(p["subtype"])
    if key:
        row[key] += 1
    own = p.get("ownership")
    row["government" if own == "Government" else
        "private" if own == "Private" else "not_specified"] += 1
    row["lat_sum"] += p["latitude"]
    row["lng_sum"] += p["longitude"]
    row["n"] += 1


def finish(row):
    row["total"] = sum(row[k] for k in COUNT_KEYS)
    row["latitude"] = row.pop("lat_sum") / row["n"]
    row["longitude"] = row.pop("lng_sum") / row["n"]
    del row["n"]
    return row


def main():
    health = load(HEALTH)
    language = load(LANGUAGE)
    points = health + language
    points, edited, dropped = apply_overrides(points)
    if edited or dropped:
        print(f"manual overrides applied: {edited} edited, {dropped} dropped")

    for p in points:
        p["city"] = norm_city(p.get("city"))

    states, city_rows = {}, {}
    for p in points:
        st = p.get("state") or "(unspecified)"
        states.setdefault(st, blank_row({"state": st}))
        tally(states[st], p)
        city = p["city"]
        if not city:
            continue
        key = (st, city)
        city_rows.setdefault(key, blank_row({"state": st, "city": city}))
        tally(city_rows[key], p)

    states_out = [finish(r) for _, r in sorted(states.items())]
    # State first, then city, so the table groups every city under its state.
    cities_out = [finish(r) for _, r in sorted(city_rows.items())]

    def coverage(layer, rows):
        placed = sum(1 for p in rows if p["city"])
        return {"layer": layer, "points": len(rows), "cityAttributed": placed,
                "cityMissing": len(rows) - placed}

    cov = {
        "layers": [coverage("health", [p for p in points if p.get("domain") != "language"]),
                   coverage("language", [p for p in points if p.get("domain") == "language"])],
        "totalPoints": len(points),
        "cityAttributed": sum(1 for p in points if p["city"]),
        "cityMissing": sum(1 for p in points if not p["city"]),
        "cities": len(cities_out),
        "states": len(states_out),
        "note": ("City is parsed from free-text postal addresses for NABH rows, so a "
                 "share cannot be attributed to a city. Unattributed points still "
                 "render on the map and still count at state level. Only cities "
                 "identified in the source extracts appear here."),
    }

    json.dump(points, open(OUT_POINTS, "w", encoding="utf-8"), ensure_ascii=False)
    json.dump(states_out, open(OUT_STATES, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(cities_out, open(OUT_CITIES, "w", encoding="utf-8"), ensure_ascii=False)
    json.dump(cov, open(OUT_COVERAGE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    print(f"resolved points: {len(points)} -> {OUT_POINTS}")
    print(f"states/UTs: {len(states_out)}   cities: {len(cities_out)}")
    for l in cov["layers"]:
        print(f"  {l['layer']:9} {l['points']:6} points, "
              f"{l['cityAttributed']} city-attributed, {l['cityMissing']} without a city")


if __name__ == "__main__":
    main()
