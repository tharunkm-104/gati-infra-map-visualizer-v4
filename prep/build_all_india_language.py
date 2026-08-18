#!/usr/bin/env python3
"""
Build the all-India LANGUAGE layer -> data/all-india-language-points.json

Inputs (both under /mnt/user-data/uploads, override with env vars):
  ALL_INDIA_LANG_JSON  all-india-language-points.json
        82 points: Goethe-Institut/Zentrum (10), telc exam centres (7),
        HEIs offering German (40), SIIC proposed (25).
  IISC_TSV_SRC         all-india-language-points-other-than-telc-exam-centres-siics.txt
        A shell transcript with the IISC list embedded in a heredoc; the TSV
        block between the `cat > ... << 'ENDIISC2'` line and `ENDIISC2` is
        extracted rather than hand-copied.

  prep/sources/pdot_centres.tsv    92 PDOT/MEA pre-departure orientation centres
  prep/sources/pasch_schools.tsv   56 PASCH schools
  prep/sources/siic_operational.tsv 7 operational Skill India International Centres

SIIC comes in two flavours and they are kept apart by a `status` field:
"Operational" for the 7 live centres, "Proposed" for the 25 in the planning
list. Both roll up into the pdot_siics column, so the map shows the pipeline
while the hover card still says which is which.

Subtypes are emitted to match the keys in src/app.js ALL_INDIA_SUBTYPE_KEY.
Run from the repo root, then run prep/build_all_india_rollups.py.
"""
import csv, io, json, os, re, sys

SRC_JSON = os.environ.get(
    "ALL_INDIA_LANG_JSON",
    "/mnt/user-data/uploads/all-india-language-points.json")
SRC_IISC = os.environ.get(
    "IISC_TSV_SRC",
    "/mnt/user-data/uploads/all-india-language-points-other-than-telc-exam-centres-siics.txt")
OUT = "data/all-india-language-points.json"
PDOT_TSV = "prep/sources/pdot_centres.tsv"
PASCH_TSV = "prep/sources/pasch_schools.tsv"
SIIC_TSV = "prep/sources/siic_operational.tsv"

# Incoming subtype label -> canonical subtype used across the app.
SUBTYPE_MAP = {
    "Goethe-Institut / Goethe-Zentrum": "Goethe/PASCH/Zentrum School",
    "Goethe/TELC Exam Centre": "Goethe/TELC Exam Centre",
    "HEI Offering German": "HEI Offering German",
    "SIIC (Proposed)": "SIIC Centre",
}

STATE_NORM = {
    "andaman & nicobar": "Andaman and Nicobar Islands",
    "andaman & nicobar islands": "Andaman and Nicobar Islands",
    "jammu & kashmir": "Jammu and Kashmir",
    "dadra & nagar haveli": "Dadra and Nagar Haveli and Daman and Diu",
    "daman & diu": "Dadra and Nagar Haveli and Daman and Diu",
    "orissa": "Odisha", "pondicherry": "Puducherry",
    "nct of delhi": "Delhi", "delhi (nct)": "Delhi", "new delhi": "Delhi",
    "chandigarh (ut)": "Chandigarh",
}


def norm_state(s):
    s = (s or "").strip()
    return STATE_NORM.get(s.lower(), s)


def safe_float(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f else None  # reject NaN


def extract_iisc_rows(path):
    """Pull the TSV block out of the shell transcript heredoc."""
    text = open(path, encoding="utf-8", errors="replace").read().replace("\r\n", "\n")
    m = re.search(r"<<\s*'?(\w+)'?\n(.*?)\n\1\b", text, re.S)
    if not m:
        sys.exit(f"could not locate a heredoc block in {path}")
    return list(csv.DictReader(io.StringIO(m.group(2)), delimiter="\t"))


def main():
    points = []

    raw = json.load(open(SRC_JSON, encoding="utf-8"))
    skipped = 0
    for r in raw:
        sub = SUBTYPE_MAP.get(r.get("subtype"))
        lat, lng = safe_float(r.get("latitude")), safe_float(r.get("longitude"))
        if sub is None or lat is None or lng is None:
            skipped += 1
            continue
        points.append({
            "name": r.get("name") or "Unnamed entry",
            "domain": "language",
            "subtype": sub,
            "ownership": r.get("ownership") or "Not specified",
            "ownershipBasis": "Category-level classification (Data Sources Selected)",
            "state": norm_state(r.get("state")),
            "city": (r.get("city") or "").strip(),
            "latitude": lat, "longitude": lng,
            "coordinateStatus": r.get("coordinateStatus") or "source",
            "source": r.get("source") or "all-india-language-points.json",
        })
        if points[-1]["subtype"] == "SIIC Centre":
            points[-1]["status"] = "Proposed"

    # The 6 Goethe-Instituts and 4 Goethe-Zentren are each ALSO a Goethe exam
    # venue, so every one of them is emitted twice: once as an institution
    # (Goethe/PASCH/Zentrum School) and once as an exam centre, at the same
    # coordinate. That is deliberate and matches the 15-city pilot, where
    # "No. of Goethe / TELC / affiliated exam centres" = 10 Goethe + 7 telc = 17.
    # Kochi and Noida have telc centres but no Goethe venue, hence 12 cities
    # carrying 10 Goethe exam centres between them.
    for g in [p for p in points if p["subtype"] == "Goethe/PASCH/Zentrum School"
              and p["source"] == "City Mapping + Geocoding"]:
        venue = dict(g)
        venue["subtype"] = "Goethe/TELC Exam Centre"
        venue["name"] = f"{g['name']} (Goethe exam centre)"
        venue["dualListed"] = "Also listed as a Goethe-Institut / Zentrum institution"
        points.append(venue)

    # --- operational SIICs (the 7 live centres) ---
    for row in csv.DictReader(open(SIIC_TSV, encoding="utf-8"), delimiter="\t"):
        lat, lng = safe_float(row.get("Latitude")), safe_float(row.get("Longitude"))
        if lat is None or lng is None:
            continue
        points.append({
            "name": (row.get("Name of SIIC") or "").strip(),
            "domain": "language", "subtype": "SIIC Centre", "status": "Operational",
            "ownership": "Government",
            "ownershipBasis": "Category-level classification (Data Sources Selected)",
            "state": norm_state(row.get("State")),
            "city": (row.get("City") or "").strip(),
            "district": (row.get("District") or "").strip(),
            "latitude": lat, "longitude": lng,
            "coordinateStatus": "source", "source": "SIIC operational list",
        })

    iisc_skipped = 0
    seen = set()
    for row in extract_iisc_rows(SRC_IISC):
        lat, lng = safe_float(row.get("Latitude")), safe_float(row.get("Longitude"))
        if lat is None or lng is None:
            iisc_skipped += 1
            continue
        centre = (row.get("Training Centre Name") or "").strip()
        org = (row.get("Name of the Organisation") or "").strip()
        name = f"{centre} \u2014 {org}" if centre and org else (centre or org or "IISC centre")
        key = (name.lower(), round(lat, 6), round(lng, 6))
        if key in seen:          # the source repeats a few org/centre pairs verbatim
            iisc_skipped += 1
            continue
        seen.add(key)
        points.append({
            "name": name,
            "domain": "language",
            "subtype": "IISC Centre (PMKK)",
            "ownership": "Government",
            "ownershipBasis": "Category-level classification (Data Sources Selected)",
            "state": norm_state(row.get("State")),
            "city": (row.get("City") or "").strip(),
            "district": (row.get("District") or "").strip(),
            "status": (row.get("Status") or "").strip(),
            "latitude": lat, "longitude": lng,
            "coordinateStatus": "source",
            "source": "IISC list (NSDC)",
        })

    # --- PDOT centres (MEA pre-departure orientation) ---
    for row in csv.DictReader(open(PDOT_TSV, encoding="utf-8"), delimiter="\t"):
        lat, lng = safe_float(row.get("Latitude")), safe_float(row.get("Longitude"))
        if lat is None or lng is None:
            continue
        points.append({
            "name": f"PDOT \u2014 {(row.get('Name') or '').strip()}",
            "domain": "language", "subtype": "PDOT Centre",
            "ownership": "Government",
            "ownershipBasis": "Category-level classification (Data Sources Selected)",
            "state": norm_state(row.get("State")),
            "city": (row.get("City") or "").strip(),
            "district": (row.get("District") or "").strip(),
            "address": (row.get("Address") or "").strip(),
            "latitude": lat, "longitude": lng,
            "coordinateStatus": "source", "source": "PDOT centre list (MEA)",
        })

    # --- PASCH schools ---
    for row in csv.DictReader(open(PASCH_TSV, encoding="utf-8"), delimiter="\t"):
        lat, lng = safe_float(row.get("Latitude")), safe_float(row.get("Longitude"))
        if lat is None or lng is None:
            continue
        points.append({
            "name": (row.get("School Name") or "").strip(),
            "domain": "language", "subtype": "Goethe/PASCH/Zentrum School",
            "ownership": "Private",
            "ownershipBasis": "Category-level classification (Data Sources Selected)",
            "state": norm_state(row.get("State")),
            "city": (row.get("City") or "").strip(),
            "district": (row.get("District") or "").strip(),
            "latitude": lat, "longitude": lng,
            "coordinateStatus": "source", "source": "PASCH school list",
        })

    # Coordinates reused by three or more distinct entries are city or district
    # centroids, not street addresses -- the IISC list is reported by district.
    # Marking them pin_centroid makes them render hollow instead of implying a
    # precision the source never had.
    from collections import Counter as _C
    shared = {k for k, v in _C((round(p["latitude"], 6), round(p["longitude"], 6))
                               for p in points).items() if v >= 3}
    centroids = 0
    for p in points:
        if (round(p["latitude"], 6), round(p["longitude"], 6)) in shared:
            p["coordinateStatus"] = "pin_centroid"
            centroids += 1

    json.dump(points, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)

    from collections import Counter
    print(f"all-India language points: {len(points)} -> {OUT}")
    for k, v in Counter(p["subtype"] for p in points).most_common():
        print(f"  {k:34} {v}")
    print(f"skipped: {skipped} from JSON, {iisc_skipped} from IISC (bad coords or duplicate)")
    print(f"marked pin_centroid (coordinate shared by 3+ entries): {centroids}")


if __name__ == "__main__":
    main()
