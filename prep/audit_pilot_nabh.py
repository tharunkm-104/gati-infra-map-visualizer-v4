#!/usr/bin/env python3
"""
Audit the 15-city pilot NABH layer: reconcile the `health_facilities` column in
data/city-summary.json against the NABH points actually present in
data/infrastructure-cleaned.json, and write the result to
data/pilot-nabh-audit.json for the dashboard to report.

WHY THIS EXISTS
The consolidated table says 2,502 NABH facilities across the 15 cities. The
point file holds 3,847 NABH rows, of which 2,395 are flagged ELIGIBLE. Neither
number matches the column, in opposite directions:

  3,847 total points  >  2,502 column   because the point file kept every NABH
                                        row including corridor-ineligible ones
                                        (AYUSH, labs, imaging, blood banks,
                                        dental clinics, ethics committees).

  2,395 eligible      <  2,502 column   a 107-row shortfall: facilities the
                                        column counts but that have no eligible,
                                        renderable point behind them.

The shortfall is what this script localises. Every row it emits is a candidate
for correction in the upstream data, not a rendering fault.

Run from the repo root, after prep/reconcile_flags.py.
"""
import json
from collections import Counter, defaultdict

INFRA = "data/infrastructure-cleaned.json"
SUMMARY = "data/city-summary.json"
OUT = "data/pilot-nabh-audit.json"

RENDERABLE = {"source", "pin_centroid", "researched_override"}
NABH = "NABH Accredited Health Facility"


def main():
    infra = json.load(open(INFRA, encoding="utf-8"))
    summary = json.load(open(SUMMARY, encoding="utf-8"))
    rows = [p for p in infra if p["subtype"] == NABH]

    by_city = defaultdict(lambda: Counter())
    for p in rows:
        c = by_city[p.get("city") or "(no city)"]
        flag = p.get("eligibilityFlag") or "(none)"
        status = p.get("coordinateStatus") or "(none)"
        c["total"] += 1
        c[f"flag:{flag}"] += 1
        if status not in RENDERABLE:
            c[f"unrenderable:{status}"] += 1
        elif flag == "ELIGIBLE":
            c["eligible_renderable"] += 1

    cities = []
    for row in summary:
        city = row["city"]
        c = by_city.get(city, Counter())
        counted = row.get("health_facilities", 0) or 0
        mapped = c.get("eligible_renderable", 0)
        cities.append({
            "city": city,
            "columnCount": counted,
            "eligibleRenderablePoints": mapped,
            "shortfall": counted - mapped,
            "pointsTotal": c.get("total", 0),
            "eligible": c.get("flag:ELIGIBLE", 0),
            "uncertain": c.get("flag:UNCERTAIN", 0),
            "excluded": c.get("flag:EXCLUDED", 0),
            "unrenderable": {k.split(":", 1)[1]: v for k, v in c.items() if k.startswith("unrenderable:")},
        })

    out = {
        "columnTotal": sum(c["columnCount"] for c in cities),
        "eligibleRenderableTotal": sum(c["eligibleRenderablePoints"] for c in cities),
        "shortfallTotal": sum(c["shortfall"] for c in cities),
        "pointsTotal": len(rows),
        "byFlag": dict(Counter(p.get("eligibilityFlag") or "(none)" for p in rows)),
        "byCoordinateStatus": dict(Counter(p.get("coordinateStatus") or "(none)" for p in rows)),
        "cities": cities,
        "note": ("The shortfall is the number of facilities the consolidated table counts "
                 "that have no eligible, renderable NABH point behind them. Causes to check "
                 "upstream: rows collapsed by name+PIN de-duplication that were in fact "
                 "distinct facilities; rows whose address failed to yield a city; and rows "
                 "classified UNCERTAIN whose facility type could not be resolved. Every "
                 "shortfall row is a data-validation candidate, not a map bug."),
    }
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    print(f"column total {out['columnTotal']}, eligible+renderable {out['eligibleRenderableTotal']}, "
          f"shortfall {out['shortfallTotal']}")
    print(f"NABH points in file: {out['pointsTotal']}  by flag: {out['byFlag']}")
    print(f"by coordinate status: {out['byCoordinateStatus']}")
    print()
    print(f"{'city':30} {'column':>7} {'mapped':>7} {'short':>6} {'uncertain':>10} {'excluded':>9}")
    for c in sorted(out["cities"], key=lambda r: -r["shortfall"]):
        print(f"{c['city']:30} {c['columnCount']:7} {c['eligibleRenderablePoints']:7} "
              f"{c['shortfall']:6} {c['uncertain']:10} {c['excluded']:9}")


if __name__ == "__main__":
    main()
