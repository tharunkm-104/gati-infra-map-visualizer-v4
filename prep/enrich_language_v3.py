#!/usr/bin/env python3
"""
v3 language-side enrichment of data/infrastructure-cleaned.json + data/cities.json.

  1. Adds 17 Goethe/TELC exam-centre points (10 Goethe-Institut/Zentrum,
     coordinates from the 'City Mapping + Geocoding' sheet; 7 telc centres,
     coordinates supplied directly) as a new renderable subtype.
  2. Tags every point with `ownership` + `ownershipBasis` per the fixed
     category rules from the 'Data Sources Selected' sheet:
       Goethe / PASCH / Zentrum / exam centres   -> Private   (category rule)
       PDOT / SIIC / IISC                        -> Government(category rule)
       HEI Offering German                       -> per-institute lookup
       NABH / NMC / INC                          -> see build_all_india_health.py
  3. Recomputes each city's exam_centres count from the points actually placed
     in that city, and carries the delta through the derived totals.

Idempotent: re-running against already-enriched data produces the same result.
Run from the repo root: python3 prep/enrich_language_v3.py
"""
import json

INFRA_PATH = "data/infrastructure-cleaned.json"
CITIES_PATH = "data/cities.json"

EXAM_SUBTYPE = "Goethe/TELC Exam Centre"

# City names here are normalised to match the `city` field in data/cities.json
# (e.g. the pilot treats Coimbatore North + South as one row).
GOETHE_POINTS = [
    ("Goethe-Institut / Max Mueller Bhavan, Kasturba Gandhi Marg, Connaught Place", "New Delhi", "Delhi (NCT)", 28.623891, 77.224235),
    ("Goethe-Institut / Max Mueller Bhavan, CMH Road, Indiranagar", "Bengaluru", "Karnataka", 12.9782458, 77.6443028),
    ("Goethe-Institut / Max Mueller Bhavan, K. Dubash Marg, Kala Ghoda", "Mumbai", "Maharashtra", 18.9275177, 72.8324551),
    ("Goethe-Institut / Max Mueller Bhavan, Boat Club Road, Sangamvadi", "Pune", "Maharashtra", 18.5382663, 73.877459),
    ("Goethe-Institut / Max Mueller Bhavan, Rutland Gate 5th Street, Nungambakkam", "Chennai", "Tamil Nadu", 13.0601092, 80.2514838),
    ("Goethe-Institut / Max Mueller Bhavan, Park Mansions, Park Street", "Kolkata", "West Bengal", 22.552721, 88.3535642),
    ("Goethe-Zentrum Chandigarh, SCO 362-363, Sector 34-A", "Chandigarh", "Chandigarh (UT)", 30.7227025, 76.7678664),
    ("Goethe-Zentrum Trivandrum, Allianz Haus, Jawahar Nagar", "Thiruvananthapuram", "Kerala", 8.5160258, 76.9669794),
    ("Goethe-Zentrum Coimbatore, Avinashi Road", "Coimbatore North + South", "Tamil Nadu", 11.0067499, 76.9777732),
    ("Goethe-Zentrum Hyderabad, Journalist Colony, Banjara Hills", "Hyderabad", "Telangana", 17.416889, 78.43867),
]

TELC_POINTS = [
    ("University of Mumbai \u2014 Department of German (telc)", "Mumbai", "Maharashtra", 19.0708364, 72.8577789),
    ("Indo-German Chamber of Commerce (telc)", "Mumbai", "Maharashtra", 18.9335634, 72.8259357),
    ("Quadrigo Private Limited (telc)", "Bengaluru", "Karnataka", 12.9668006, 77.6483188),
    ("Lingua Leaps Educentre Pvt. Ltd. (telc)", "Noida", "Uttar Pradesh", 28.5657595, 77.3169944),
    ("BSLEU Akademie LLP. (telc)", "Noida", "Uttar Pradesh", 28.6137442, 77.3666594),
    ("PSG Institute of Advanced Studies (telc)", "Coimbatore North + South", "Tamil Nadu", 11.0262513, 77.0195323),
    ("Deutsche Fachkr\u00e4fteagentur f\u00fcr Gesundheits- und Pflegeberufe GmbH (telc)", "Kochi", "Kerala", 10.0656147, 76.3228717),
]

# HEI government/private mapping, as supplied (AISHE institute list). Institute
# names in infrastructure-cleaned.json are stored without the trailing city
# clause ("Panjab University" vs "Panjab University,Chandigarh"), so matching is
# exact-first, then unique-substring.
HEI_OWNERSHIP = {
    "pt. ravishankar shukla university, raipur": "Government",
    "central university of gujarat": "Government",
    "kurukshetra university, kurukshetra": "Government",
    "maharshi dayanand university, rohtak": "Government",
    "himachal pradesh university , shimla": "Government",
    "cochin university of science & technology, kochi": "Government",
    "guru nanak dev university, amritsar": "Government",
    "mohan lal sukhadia university, udaipur": "Government",
    "dr. b. r. ambedkar university, agra": "Government",
    "aligarh muslim university, aligarh": "Government",
    "chatrapati sahuji maharaj kanpur university, kanpur": "Government",
    "banaras hindu university, banaras": "Government",
    "doon university, dehradun": "Government",
    "visva bharati, shantiniketan": "Government",
    "indira gandhi national open university": "Government",
    "maharaja sayajirao university of baroda, vadodara": "Government",
    "shri vishwakarma skill university": "Government",
    "university of kashmir, srinagar": "Government",
    "karnataka university, dharwad": "Government",
    "university of mysore, mysore": "Government",
    "mgm university": "Private",
    "amity university rajasthan, jaipur": "Private",
    "the english and foreign languages university, hyderabad": "Government",
    "panjab university,chandigarh": "Government",
    "university of delhi": "Government",
    "bharati college": "Government",
    "dr. babasaheb ambedkar marathwada university, chhatrapati sambhajinagar": "Government",
    "shivaji university, kolhapur": "Government",
    "savitribai phule pune university": "Government",
    "symbiosis international (deemed university), pune": "Private",
    "university of rajasthan": "Government",
    "sri guru teg bahadur khalsa college": "Government",
    "satyawati college": "Government",
    "university of mumbai": "Government",
    "bansilal ramnath agarwal charitable trusts vishwakarma college of arts, science and commerce college,pune": "Private",
    "nowgong college": "Government",
    "daulat ram college": "Government",
    "sri venkateswara college": "Government",
    "assumption college, changanacherry 686 101": "Private",
    "marathwada mitra mandal's college of commerce, pune 4": "Private",
}

CATEGORY_RULE = {
    "Goethe/PASCH/Zentrum School": "Private",
    EXAM_SUBTYPE: "Private",
    "PDOT Centre": "Government",
    "SIIC Centre": "Government",
    "IISC Centre (PMKK)": "Government",
}


def norm(s):
    return " ".join((s or "").strip().lower().split())


def hei_ownership(name):
    """Exact match, then unique-substring match. Ambiguity is never guessed."""
    n = norm(name)
    if n in HEI_OWNERSHIP:
        return HEI_OWNERSHIP[n], "Named in AISHE institute list"
    hits = {v for k, v in HEI_OWNERSHIP.items() if n and n in k}
    if len(hits) == 1:
        return hits.pop(), "Matched to AISHE institute list on institute name"
    return "Not specified", ("Ambiguous match in AISHE institute list"
                             if hits else "Not present in AISHE institute list")


def ownership_for_point(p):
    st = p.get("subtype")
    if st in CATEGORY_RULE:
        return CATEGORY_RULE[st], "Category-level classification (Data Sources Selected)"
    if st == "HEI Offering German":
        return hei_ownership(p.get("name"))
    if st in ("NABH Accredited Health Facility", "NMC Medical College", "INC Nursing College"):
        return "Not specified", "Category flagged Both; no per-facility field in source"
    return "Not specified", ""


def main():
    infra = json.load(open(INFRA_PATH, encoding="utf-8"))
    cities = json.load(open(CITIES_PATH, encoding="utf-8"))

    # Idempotency: drop any exam-centre points from a previous run before re-adding.
    infra = [p for p in infra if p.get("subtype") != EXAM_SUBTYPE]

    new_points = []
    for name, city, state, lat, lng in GOETHE_POINTS + TELC_POINTS:
        new_points.append({
            "name": name, "domain": "language", "subtype": EXAM_SUBTYPE,
            "city": city, "state": state, "district": city,
            "latitude": lat, "longitude": lng, "coordinateStatus": "source",
        })
    infra.extend(new_points)

    for p in infra:
        p["ownership"], p["ownershipBasis"] = ownership_for_point(p)

    exam_by_city = {}
    for p in new_points:
        exam_by_city[p["city"]] = exam_by_city.get(p["city"], 0) + 1

    known = {c["city"] for c in cities}
    outside = {k: v for k, v in exam_by_city.items() if k not in known}

    changes = []
    for c in cities:
        old = c.get("exam_centres", 0) or 0
        new = exam_by_city.get(c["city"], 0)
        if new != old:
            delta = new - old
            c["exam_centres"] = new
            for field in ("formal_german_raw", "language_total", "grand_total"):
                c[field] = (c.get(field, 0) or 0) + delta
            changes.append((c["city"], old, new))

    json.dump(infra, open(INFRA_PATH, "w", encoding="utf-8"), ensure_ascii=False)
    json.dump(cities, open(CITIES_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    print(f"infrastructure points: {len(infra)} (+{len(new_points)} exam centres)")
    heis = [p for p in infra if p["subtype"] == "HEI Offering German"]
    matched = [p for p in heis if p["ownership"] != "Not specified"]
    print(f"HEI ownership matched: {len(matched)}/{len(heis)}")
    for p in heis:
        if p["ownership"] == "Not specified":
            print(f"  UNMATCHED HEI: {p['name']}")
    print("exam_centres changed:", changes or "none")
    if outside:
        print("exam centres outside the 15 pilot cities (mapped, not counted):", outside)


if __name__ == "__main__":
    main()
