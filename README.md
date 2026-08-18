# Infrastructure Map

Static, GitHub Pages-ready visualizer for the 15 shortlisted Indian cities and at all-India level, in the
German-language and health-infrastructure analysis.

## What this version shows

- Zoom levels: **Automatic**, **State**, **City**, **Infrastructure** (no district tier).
- Three view modes, raw counts only, no derived/composite scores:
  1. **Language vs Health** (default) — blue = language infrastructure, green = health infrastructure.
  2. **By category pair** — NMC Medical Colleges / NABH Health Facilities / INC Nursing Colleges split out on
     the health side; Formal German Infrastructure vs General Skilling Infrastructure on the language side.
  3. **Fully disaggregated** — all 9 raw source categories, each its own color.
- At State/City zoom, bubbles are colored by a fixed per-location color (not by domain), sized by the total
  of whatever the active view mode is counting.
- At Infrastructure zoom, individual points render from `data/infrastructure-cleaned.json`, colored per the
  active view mode.
- Hover (not click) shows a short detail card after ~550ms: counts at State/City level, or
  name/category/city at Infrastructure level.
- Below the zoom-level buttons: a plain table, one row per state or city, columns = the active view mode's
  raw count categories. No ranking, no computed column.

## Known data gaps — do not paper over these

- Individual **Infrastructure**-zoom points for PDOT/SIIC/IISC collapse into one subtype,
  "General Skilling Infrastructure (PDOT/SIIC/IISC)", because the source sheet doesn't retain which of the
  three a merged row came from. City/state tables still show `pdot_siics` and `iiscs` as separate counts.
- **Private German training organisations** (`private_training`) and **Goethe/TELC exam centres**
  (`exam_centres`) have no individually geocoded rows anywhere in the source sheets — they exist only as
  city/state totals. They will never appear as dots at Infrastructure zoom; that's correct, not a bug.
- There is no **ownership (Govt./Private)** field or per-facility capacity parameter in any source file.
  The Infrastructure-zoom hover card says so explicitly rather than guessing.

## Coordinate cleanup

`prep/normalize.py` never reuses a flagged coordinate as-is: if a researched override isn't present in
`COORDINATE_OVERRIDES`, the row is written with `latitude`/`longitude: null` and
`coordinateStatus: "undefined_flagged"`. The browser filters those out (plus missing-coordinate and `(0,0)`
rows) before clustering and logs the result as
`[infrastructure-layer] renderable=... dropped=... total=...`.

As of the last data pull: **4,681** scoped rows, **4,377** renderable, **304** dropped (303
`undefined_flagged`, 1 other invalid coordinate). The drop is concentrated in **INC Nursing Colleges**
(262 of 506 nursing-college rows — about half) and **General Skilling Infrastructure** (38 of 118 rows);
every other category lost 2 rows or fewer. Re-run `prep/normalize.py` after any source-sheet update to
refresh these counts — `data/*.json` in this repo is a point-in-time snapshot, not regenerated automatically.

## Local preview

Run a static file server from this folder, then open `src/index.html`.

```powershell
python -m http.server 5177 --bind 127.0.0.1
```

Then visit `http://127.0.0.1:5177/src/index.html`.


# prep/ — data pipeline

Every JSON in `data/` is generated. Run from the **repo root**, not from inside
`prep/`, because the scripts use paths like `data/all-india-states.json`.

```bash
cd gati-infra-map-visualizer-v3
python3 prep/build_all_india_health.py         # 1
python3 prep/build_all_india_language.py       # 2
python3 prep/build_all_india_rollups.py        # 3  always last
python3 prep/flag_out_of_india.py              # 4  audit, AFTER step 3
python3 prep/audit_pilot_nabh.py               # audit, any time
python3 prep/audit_pilot_reconciliation.py     # audit, any time
```

## Why the order matters

Steps 1 and 2 each write a *point* file and nothing else. Step 3 reads **both**
point files, applies `data/manual-overrides.json`, and writes everything the
dashboard actually loads.

Re-run step 2 alone and stop, and the point file is fresh while the tables and
the map still hold the previous run's data. **Any time you touch a source or an
override, finish with step 3.** Steps 1 and 2 are independent of each other. The
audit scripts only read; they never feed the dashboard.

## The dashboard reads the RESOLVED point file

`src/app.js` fetches `data/all-india-points.json` — both layers merged with
`manual-overrides.json` applied — not the two raw `*-points.json` files. That is
why step 3 is mandatory: without it a hand correction reaches the tables but
never the map. The raw layers stay untouched, so a correction is always visible
as a diff against them.

## Fixing bad coordinates

```bash
python3 prep/flag_out_of_india.py               # writes data/out-of-india-points.csv
# fill in corrected_latitude / corrected_longitude
python3 prep/apply_coordinate_corrections.py    # --dry-run first if you like
python3 prep/build_all_india_rollups.py         # corrections reach map + tables
```

`apply_coordinate_corrections.py` writes nothing unless every row passes: the
corrected coordinate parses as a number, lands inside India, and the match
criteria identify exactly one point. It tags its own rules, so re-running
replaces them rather than accumulating duplicates, and leaves hand-written rules
alone.

| Script | Reads | Writes |
|---|---|---|
| `build_all_india_health.py` | workbook, `nabh_raw_rows.jsonl` | `all-india-health-points.json` |
| `build_all_india_language.py` | `prep/sources/*.tsv`, uploaded language JSON | `all-india-language-points.json` |
| `build_all_india_rollups.py` | both point files, `manual-overrides.json` | **`all-india-points.json`**, states, cities, coverage |
| `flag_out_of_india.py` | `all-india-points.json`, pilot layer | `out-of-india-points.csv` |
| `apply_coordinate_corrections.py` | corrected `out-of-india-points.csv` | rules in `manual-overrides.json` |
| `audit_pilot_nabh.py` | pilot layer, `city-summary.json` | `pilot-nabh-audit.json` |
| `audit_pilot_reconciliation.py` | pilot layer, `cities.json` | `pilot-reconciliation.csv` |
| `enrich_language_v3.py` | pilot layer | rewrites `infrastructure-cleaned.json`, `cities.json` |
| `normalize.py`, `reconcile_flags.py` | 15-city pilot sources | `infrastructure-cleaned.json` |

## Two source paths are absolute

`build_all_india_health.py` and `build_all_india_language.py` point at
`/mnt/user-data/uploads/...` for the workbook, the NABH JSONL and the uploaded
language JSON. Those files are **not in the repo** (the JSONL alone is 8 MB).
Before running on another machine, either move them into the repo and update the
constants at the top of each script, or set the env vars the language script
supports (`ALL_INDIA_LANG_JSON`, `IISC_TSV_SRC`).

Everything in `prep/sources/` **is** in the repo and is hand-maintained.

## Hand corrections

`data/manual-overrides.json`, applied at step 3. See the `_readme` inside it.
Never hand-edit the generated point files; they are overwritten on every run.
