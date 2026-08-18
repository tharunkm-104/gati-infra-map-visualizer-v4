const format = new Intl.NumberFormat("en-IN");
const HOVER_DELAY_MS = 550;

// ---- GATI palette tokens ----
// Health scale: NABH recedes into the basemap grey, colleges pop.
// Language/skilling scale: warm orange + gold steps, entirely separate from health hues.
// Guidebook primaries: teal #006B76, deep teal #00333A, yellow #E5A812,
// light gold #FFCC4E, sky #84D2E2, brown #573D00, greys #839097 / #D8E2E7.
// Series colours below are spaced for contrast: health sits on the teal->cyan
// axis, language on the yellow->brown axis, and no two adjacent series share a
// lightness step. `ink: true` marks fills too light for white label text.
const GATI = {
  teal: "#006B76",
  tealDeep: "#00333A",
  tealDark: "#00333A",
  sky: "#84D2E2",
  cyan: "#2E9BAF",
  yellow: "#E5A812",
  goldLight: "#FFCC4E",
  brown: "#573D00",
  rust: "#B04A00",
  olive: "#7D8C3F",
  grey: "#839097",
  greyLight: "#D8E2E7",
  ink: "#101A18",
};

// Health series -- deep teal / mid cyan / grey. NABH stays recessive because it
// outnumbers the colleges by an order of magnitude.
const C_NABH = GATI.grey;
const C_NMC = GATI.tealDeep;
const C_INC = GATI.cyan;
// Language series -- yellow through brown, each a clear step apart.
const C_GOETHE = GATI.yellow;
const C_EXAM = GATI.goldLight;
const C_HEI = GATI.rust;
const C_PDOT = GATI.brown;
const C_SIIC = GATI.teal;
const C_IISC = GATI.olive;
const C_PRIVATE_LANG = GATI.grey;

// Fills light enough that white label text would fail contrast.
const LIGHT_FILLS = new Set([GATI.goldLight, GATI.sky, GATI.greyLight]);
function labelInk(color) {
  return LIGHT_FILLS.has(color) ? GATI.ink : "#ffffff";
}

// ---- view mode definitions (raw counts only, no derived scores) ----
const VIEW_MODES = {
  domain: {
    label: "Language & Health",
    series: [
      { key: "language_total", label: "Language Infrastructure", color: C_GOETHE },
      { key: "health_total", label: "Health Infrastructure", color: C_NMC },
    ],
  },
  pairs: {
    label: "By Sector",
    series: [
      { key: "formal_german_raw", label: "Formal German Infrastructure (Goethe/PASCH/Zentrum + HEIs + Exam Centres)", color: C_GOETHE },
      { key: "general_skilling_raw", label: "General Skilling Infrastructure (PDOT/SIIC/IISC)", color: C_PDOT },
      { key: "nursing_colleges", label: "INC Nursing Colleges", color: C_INC },
      { key: "medical_colleges", label: "NMC Medical Colleges", color: C_NMC },
      { key: "health_facilities", label: "NABH Accredited Health Facilities", color: C_NABH },
    ],
  },
  full: {
    label: "By Category",
    series: [
      { key: "goethe_schools", label: "Goethe/PASCH/Zentrum Schools", color: C_GOETHE },
      { key: "heis_german", label: "HEIs Offering German", color: C_HEI },
      { key: "exam_centres", label: "Goethe/TELC Exam Centres", color: C_EXAM },
      { key: "pdot_centres", label: "PDOT Centres", color: C_PDOT },
      { key: "siic_centres", label: "SIIC Centres", color: C_SIIC },
      { key: "iiscs", label: "IISC Centres", color: C_IISC },
      { key: "nursing_colleges", label: "INC Nursing Colleges", color: C_INC },
      { key: "medical_colleges", label: "NMC Medical Colleges", color: C_NMC },
      { key: "health_facilities", label: "NABH Accredited Health Facilities", color: C_NABH },
    ],
  },
};

// Individual infrastructure points carry these subtypes. Exam Centres and
// Private German Training Organisations have no individually geocoded points in
// the source data -- they only exist as city/state totals, so their legend chips
// toggle a table column but no dots.
const POINT_SUBTYPE_META = {
  "Goethe/PASCH/Zentrum School": { domain: "language", pairsKey: "formal_german_raw", fullKey: "goethe_schools" },
  "HEI Offering German": { domain: "language", pairsKey: "formal_german_raw", fullKey: "heis_german" },
  "Goethe/TELC Exam Centre": { domain: "language", pairsKey: "formal_german_raw", fullKey: "exam_centres" },
  "PDOT Centre": { domain: "language", pairsKey: "general_skilling_raw", fullKey: "pdot_centres" },
  "SIIC Centre": { domain: "language", pairsKey: "general_skilling_raw", fullKey: "siic_centres" },
  "IISC Centre (PMKK)": { domain: "language", pairsKey: "general_skilling_raw", fullKey: "iiscs" },
  // Retained only for rows that could not be matched back to a source section.
  "General Skilling Infrastructure (PDOT/SIIC/IISC)": { domain: "language", pairsKey: "general_skilling_raw", fullKey: "pdot_centres" },
  "NABH Accredited Health Facility": { domain: "health", pairsKey: "health_facilities", fullKey: "health_facilities" },
  "NMC Medical College": { domain: "health", pairsKey: "medical_colleges", fullKey: "medical_colleges" },
  "INC Nursing College": { domain: "health", pairsKey: "nursing_colleges", fullKey: "nursing_colleges" },
};

const DOMAIN_COLOR = { language: C_GOETHE, health: C_NMC };
const FALLBACK_COLOR = GATI.grey;

// Darker schemes only: schemeSet3 pastels made white bubble labels unreadable.
const CITY_PALETTE = [...d3.schemeTableau10, ...d3.schemeDark2, ...d3.schemeCategory10];
let cityColorScale = null;
let stateColorScale = null;
let allIndiaStateColorScale = null;

let cities = [];
let states = [];
let infrastructure = [];
let renderableInfrastructure = [];
let trueCoordsOnly = false; // when true, hides pin_centroid ("hollow dot") points
let datasetMode = "pilot"; // "pilot" (15-city language+health) | "allIndia" (NABH+NMC+INC)
let allIndiaStates = [];
let allIndiaCities = [];
let allIndiaPoints = [];
let allIndiaCoverage = null;
let viewMode = "domain";
let forcedLevel = "auto";
let activeMarkers = [];
let activeIndex = null;
let hoverTimer = null;

// Legend filter state: which series keys are currently switched on.
// Reset to "all on" whenever the view mode changes.
let activeCategories = new Set(VIEW_MODES[viewMode].series.map((s) => s.key));

const map = L.map("map", {
  zoomControl: false,
  scrollWheelZoom: true,
}).setView([20.7, 78.9], 5);

L.control.zoom({ position: "bottomright" }).addTo(map);
L.tileLayer("https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png", {
  attribution: "&copy; OpenStreetMap contributors &copy; CARTO",
  maxZoom: 19,
}).addTo(map);

// Shared canvas renderer -- ~4,400 circleMarkers on one canvas instead of
// ~4,400 divIcon DOM nodes. This is what keeps the full-India dot view usable.
const infraCanvas = L.canvas({ padding: 0.3 });

// ---- All-India Health dataset (NABH + NMC + INC) ----
// Column names used by the all-India rollup tables. Kept as documentation of
// what data/all-india-states.json holds; GROUP_MAPPINGS is what actually maps
// these onto the view-mode series the legend and table render.
const ALL_INDIA_SUBTYPE_KEY = {
  "Goethe/PASCH/Zentrum School": "goethe_schools",
  "Goethe/TELC Exam Centre": "exam_centres",
  "HEI Offering German": "heis_german",
  "PDOT Centre": "pdot_centres",
  "SIIC Centre": "siic_centres",
  "IISC Centre (PMKK)": "iiscs",
  "NABH Accredited Health Facility": "nabh_facilities",
  "NMC Medical College": "nmc_colleges",
  "INC Nursing College": "inc_colleges",
};

function currentSeries() {
  return VIEW_MODES[viewMode].series;
}

// Every series in every view mode maps to a count column in cities.json.
function countableSeries() {
  return currentSeries();
}

function activeSeries() {
  return countableSeries().filter((s) => activeCategories.has(s.key));
}

function resetActiveCategories() {
  activeCategories = new Set(currentSeries().map((s) => s.key));
}

function safeLevel() {
  if (forcedLevel !== "auto") return forcedLevel;
  const zoom = map.getZoom();
  if (zoom <= 6) return "state";
  if (zoom <= 9) return "city";
  return "infrastructure";
}

// Only sums series that are currently switched on, so bubble sizes and the
// table stay consistent with whatever is deselected in the legend.
// All-India rows are stored with granular column names (nabh_facilities,
// goethe_schools...), but the view modes ask for pilot-shaped keys
// (health_total, formal_german_raw...). GROUP_MAPPINGS bridges the two so one
// series list drives both datasets.
//
// NOTE: general_skilling_raw deliberately omits private_training -- the
// all-India layer has no private-training data. If that ever changes, add it
// here or the "By category pair" view will under-count by exactly that column.
// Every roll-up key is ALWAYS recomputed from the eight granular columns, never
// read from a stored column. That is what makes the three view modes tally with
// each other and with the map: there is one set of underlying numbers and three
// ways of grouping it.
const COMPUTED_KEYS = {
  language_total: ["goethe_schools", "heis_german", "exam_centres", "pdot_siics", "iiscs"],
  health_total: ["health_facilities", "medical_colleges", "nursing_colleges"],
  formal_german_raw: ["goethe_schools", "heis_german", "exam_centres"],
  general_skilling_raw: ["pdot_siics", "iiscs"],
};

// The all-India rollup names three health columns differently.
const COLUMN_ALIAS = {
  health_facilities: "nabh_facilities",
  medical_colleges: "nmc_colleges",
  nursing_colleges: "inc_colleges",
};

function getRowValue(row, key) {
  const parts = COMPUTED_KEYS[key];
  if (parts) return parts.reduce((sum, k) => sum + getRowValue(row, k), 0);
  if (row[key] !== undefined) return row[key] || 0;
  const alias = COLUMN_ALIAS[key];
  return alias && row[alias] !== undefined ? row[alias] || 0 : 0;
}

// Only sums series that are currently switched on, so bubble sizes and the
// table stay consistent with whatever is deselected in the legend.
function locationTotal(row) {
  return activeSeries().reduce((sum, s) => sum + getRowValue(row, s.key), 0);
}

// The series key an individual infra point maps to under the current view mode.
// Returns null when the point's subtype has no matching series (e.g. the
// PDOT/SIIC/IISC bundle in "Fully disaggregated", which is split across three
// series that individual points cannot be attributed to).
function seriesKeyForPoint(point) {
  // Both datasets use the same subtype strings, so one lookup serves both.
  const meta = POINT_SUBTYPE_META[point.subtype];
  if (!meta) return null;
  if (viewMode === "domain") return `${meta.domain}_total`;
  const key = viewMode === "pairs" ? meta.pairsKey : meta.fullKey;
  return currentSeries().some((s) => s.key === key) ? key : null;
}

function isPointActive(point) {
  const key = seriesKeyForPoint(point);
  if (key === null) return true; // unmapped subtypes are never filtered out
  return activeCategories.has(key);
}

// NABH rows flagged EXCLUDED (AYUSH, labs, imaging, blood banks, dental
// clinics, ethics committees) are not corridor-relevant and never render. They
// stay in the data file; reconcile_flags.py remains the place to change a flag.
// UNCERTAIN rows do render, and render solid -- their eligibility is unresolved
// but their coordinates are fine, so flagging them visually was misleading.
function isEligiblePilotPoint(p) {
  if (p.subtype !== "NABH Accredited Health Facility") return true;
  return p.eligibilityFlag !== "EXCLUDED";
}

// Hollow means one thing only: the coordinate is approximate (a PIN-code
// centroid, or a point shared with another institution).
function isProvisionalPoint(p) {
  return p.coordinateStatus === "pin_centroid";
}

function coordinateFilteredInfrastructure() {
  return renderableInfrastructure.filter(
    (p) => isEligiblePilotPoint(p) && (!trueCoordsOnly || p.coordinateStatus !== "pin_centroid")
  );
}

function pointsForLevel(level) {
  if (datasetMode === "allIndia") {
    if (level === "state") return allIndiaStates.map((s) => ({ ...s, levelName: s.state }));
    if (level === "city") return allIndiaCities.map((c) => ({ ...c, levelName: c.city }));
    return allIndiaPoints.filter(isPointActive);
  }
  if (level === "state") return states.map((s) => ({ ...s, levelName: s.state }));
  if (level === "city") return cities.map((c) => ({ ...c, levelName: c.city }));
  return coordinateFilteredInfrastructure().filter(isPointActive);
}

function featureForPoint(point, level) {
  return {
    type: "Feature",
    geometry: { type: "Point", coordinates: [point.longitude, point.latitude] },
    properties: { ...point, level },
  };
}

// State/city levels still cluster. Infrastructure level does NOT -- every dot is
// drawn individually at any zoom, so wide zoom-outs no longer collapse into
// grey count-bubbles.
function buildIndex(level) {
  if (level === "infrastructure") {
    activeIndex = null;
    return;
  }
  const points = pointsForLevel(level).filter((p) => Number.isFinite(p.latitude) && Number.isFinite(p.longitude));
  const features = points.map((p) => featureForPoint(p, level));
  activeIndex = new Supercluster({
    radius: 44,
    maxZoom: 11,
    map: (props) => ({ count: 1, total: locationTotal(props) }),
    reduce: (accumulated, props) => {
      accumulated.count += props.count;
      accumulated.total += props.total;
    },
  }).load(features);
}

function clearMarkers() {
  activeMarkers.forEach((m) => m.remove());
  activeMarkers = [];
}

function drawMarkers() {
  const level = safeLevel();
  clearMarkers();
  buildIndex(level);
  const bounds = map.getBounds().pad(0.2);

  if (level === "infrastructure") {
    // Raw dot mode: no clustering, canvas-rendered circle markers.
    pointsForLevel("infrastructure").forEach((point) => {
      if (!Number.isFinite(point.latitude) || !Number.isFinite(point.longitude)) return;
      if (!bounds.contains([point.latitude, point.longitude])) return;
      const marker = infrastructureMarker(point, point.latitude, point.longitude);
      marker.addTo(map);
      activeMarkers.push(marker);
    });
    renderTable(level);
    return;
  }

  const bbox = [bounds.getWest(), bounds.getSouth(), bounds.getEast(), bounds.getNorth()];
  const clusters = activeIndex.getClusters(bbox, Math.round(map.getZoom()));
  clusters.forEach((feature) => {
    const [longitude, latitude] = feature.geometry.coordinates;
    const props = feature.properties;
    const marker = props.cluster
      ? clusterMarker(feature, level, latitude, longitude)
      : pointMarker(feature, level, latitude, longitude);
    marker.addTo(map);
    activeMarkers.push(marker);
  });
  renderTable(level);
}

// Square-root so AREA tracks the count (a linear radius makes a big state look
// several times larger than it is), then clamped to a narrow band so dense
// states cannot swallow the map at city level.
const BUBBLE_MIN = 18;
const BUBBLE_MAX = 44;

function radiusForTotal(total, maxTotal) {
  if (!(total > 0) || !(maxTotal > 0)) return BUBBLE_MIN;
  const ratio = Math.sqrt(Math.min(total, maxTotal) / maxTotal);
  return Math.round(BUBBLE_MIN + ratio * (BUBBLE_MAX - BUBBLE_MIN));
}

// The table/bubble rows behind a given zoom level, for whichever dataset is on.
function rowsForLevel(level) {
  if (datasetMode === "allIndia") return level === "city" ? allIndiaCities : allIndiaStates;
  return level === "state" ? states : cities;
}

function maxTotalForLevel(level) {
  const rows = rowsForLevel(level);
  return Math.max(1, ...rows.map((r) => locationTotal(r)));
}

function clusterMarker(feature, level, latitude, longitude) {
  const props = feature.properties;
  const maxTotal = maxTotalForLevel(level);
  const size = radiusForTotal(props.total, maxTotal);
  const marker = L.marker([latitude, longitude], {
    icon: L.divIcon({
      html: `<div class="cluster-bubble" style="width:${size}px;height:${size}px;background:#5b6673">${format.format(props.point_count)}</div>`,
      className: "",
      iconSize: [size, size],
      iconAnchor: [size / 2, size / 2],
    }),
  });
  marker.on("click", () => {
    const expansionZoom = Math.min(activeIndex.getClusterExpansionZoom(props.cluster_id), 16);
    map.setView([latitude, longitude], expansionZoom);
  });
  bindHover(marker, () => clusterHoverHtml(level, props));
  return marker;
}

function clusterHoverHtml(level, props) {
  return `<strong>${format.format(props.point_count)} ${level === "state" ? "states" : "cities"} clustered</strong><div>Total ${VIEW_MODES[viewMode].label.toLowerCase()}: ${format.format(props.total)}</div>`;
}

function pointMarker(feature, level, latitude, longitude) {
  const point = feature.properties;
  const maxTotal = maxTotalForLevel(level);
  const total = locationTotal(point);
  const size = radiusForTotal(total, maxTotal);
  const colorScale = datasetMode === "allIndia" ? allIndiaStateColorScale : level === "state" ? stateColorScale : cityColorScale;
  const color = colorScale(point.levelName);
  const marker = L.marker([latitude, longitude], {
    icon: L.divIcon({
      html: `<div class="marker-bubble" style="width:${size}px;height:${size}px;background:${color}">${format.format(total)}</div>`,
      className: "",
      iconSize: [size, size],
      iconAnchor: [size / 2, size / 2],
    }),
  });
  bindHover(marker, () => locationHoverHtml(point));
  return marker;
}

function locationHoverHtml(point) {
  const rows = countableSeries()
    .map((s) => {
      const off = activeCategories.has(s.key) ? "" : " hover-row--off";
      return `<div class="hover-row${off}"><span>${s.label}</span><b>${format.format(getRowValue(point, s.key))}</b></div>`;
    })
    .join("");
  return `<strong>${point.levelName}</strong>${rows}`;
}

// Canvas circleMarker -- cheap enough to draw every point at any zoom.
function infrastructureMarker(point, latitude, longitude) {
  const color = pointColor(point);
  // Approximate coordinates (PIN-code centroids, shared points) render hollow:
  // coloured ring, no fill, so precision is visible at a glance.
  const approximate = isProvisionalPoint(point);
  const marker = L.circleMarker([latitude, longitude], {
    renderer: infraCanvas,
    radius: approximate ? 5 : 4.5,
    weight: approximate ? 1.6 : 1,
    color: approximate ? color : "#ffffff",
    opacity: approximate ? 1 : 0.9,
    fillColor: color,
    fillOpacity: approximate ? 0 : 0.95,
  });
  bindHover(marker, () => infrastructureHoverHtml(point));
  return marker;
}

function pointColor(point) {
  const meta = POINT_SUBTYPE_META[point.subtype];
  if (!meta) return FALLBACK_COLOR;
  if (viewMode === "domain") return DOMAIN_COLOR[meta.domain];
  const key = viewMode === "pairs" ? meta.pairsKey : meta.fullKey;
  const series = currentSeries().find((s) => s.key === key);
  return series ? series.color : FALLBACK_COLOR;
}

function infrastructureDetailRows(point) {
  const fields = [
    ["Facility type", point.facilityType],
    ["Ownership", point.ownership],
    ["Status", point.status],
  ];
  return fields
    .filter(([, value]) => value)
    .map(([label, value]) => `<div class="hover-row"><span>${label}</span><b>${value}</b></div>`)
    .join("");
}

const STATUS_LABEL = {
  source: "As given in source data",
  pin_centroid: "Approximate \u2014 PIN-code centroid or point shared with another institution",
  researched_override: "Corrected \u2014 source coordinate was wrong, replaced after research",
};

function infrastructureHoverHtml(point) {
  const status = STATUS_LABEL[point.coordinateStatus] || point.coordinateStatus;
  return `
    <strong>${point.name || "Unnamed entry"}</strong>
    <div class="hover-row"><span>Category</span><b>${point.subtype}</b></div>
    <div class="hover-row"><span>City</span><b>${point.city}</b></div>
    ${infrastructureDetailRows(point)}
    <div class="hover-note">Coordinate: ${status}.${
      point.ownershipBasis ? ` Ownership: ${point.ownershipBasis.toLowerCase()}.` : ""
    }</div>
  `;
}

// ---- hover card ----
const hoverCard = document.getElementById("hover-card");

function bindHover(marker, htmlFn) {
  marker.on("mouseover", (e) => {
    clearTimeout(hoverTimer);
    hoverTimer = setTimeout(() => showHoverCard(htmlFn(), e.originalEvent), HOVER_DELAY_MS);
  });
  marker.on("mousemove", (e) => {
    if (!hoverCard.hidden) positionHoverCard(e.originalEvent);
  });
  marker.on("mouseout", () => {
    clearTimeout(hoverTimer);
    hoverCard.hidden = true;
  });
}

function showHoverCard(html, originalEvent) {
  hoverCard.innerHTML = html;
  hoverCard.hidden = false;
  positionHoverCard(originalEvent);
}

function positionHoverCard(originalEvent) {
  if (!originalEvent) return;
  const mapRect = document.getElementById("map").getBoundingClientRect();
  hoverCard.style.left = `${originalEvent.clientX - mapRect.left + 16}px`;
  hoverCard.style.top = `${originalEvent.clientY - mapRect.top + 16}px`;
}

// ---- aggregate summary strip ----
// Fixed totals across all 15 cities, summed from cities.json. Deliberately NOT
// derived from visible dots: that would be expensive and would change on pan.
// Refreshed on view-mode change and initial load only.
function mappedPointCounts() {
  const counts = new Map();
  const source = datasetMode === "allIndia" ? allIndiaPoints : coordinateFilteredInfrastructure();
  source.forEach((point) => {
    const key = seriesKeyForPoint(point);
    if (key) counts.set(key, (counts.get(key) || 0) + 1);
  });
  return counts;
}

function renderAggregateSummary() {
  const host = document.getElementById("aggregate-summary");
  if (!host) return;

  const allIndia = datasetMode === "allIndia";
  const rows = allIndia ? allIndiaStates : cities;
  if (!rows.length) {
    host.innerHTML = "";
    return;
  }

  // Every figure below comes from the same rows the table renders, resolved
  // through getRowValue. The per-category numbers therefore always sum to the
  // headline, in every view mode, for both datasets.
  let total = 0;
  const items = countableSeries()
    .map((s) => {
      const counted = rows.reduce((sum, r) => sum + getRowValue(r, s.key), 0);
      const on = activeCategories.has(s.key);
      if (on) total += counted;
      const off = on ? "" : " summary-item--off";
      return `<div class="summary-item${off}">
        <span class="swatch" style="background:${s.color}"></span>
        <b>${format.format(counted)}</b>
        <span class="summary-label">${s.label}</span>
      </div>`;
    })
    .join("");

  const scope = allIndia
    ? `All India &middot; ${rows.length} states/UTs`
    : `15 cities`;

  host.innerHTML =
    `<div class="summary-title">${scope} &middot; ${format.format(total)} facilities</div>` +
    `<div class="summary-items">${items}</div>`;
}

// ---- legend ----
const OWNERSHIP_COLORS = { Government: GATI.teal, Private: GATI.rust, "Not specified": GATI.grey };

function renderLegend() {
  const legend = document.getElementById("legend");
  const level = safeLevel();
  if (level === "infrastructure") {
    const categoryChips = currentSeries()
      .map((s) => {
        const on = activeCategories.has(s.key);
        const style = on
          ? `background:${s.color};border-color:${s.color};color:${labelInk(s.color)};`
          : `background:transparent;border-color:${s.color};color:${s.color};`;
        const dot = on ? labelInk(s.color) : s.color;
        const note = s.countsOnly ? '<span class="chip-note">counts only</span>' : "";
        return `<button type="button" class="legend-chip${on ? " active" : ""}" data-key="${s.key}" aria-pressed="${on}" style="${style}"><span class="chip-dot" style="background:${dot}"></span>${s.label}${note}</button>`;
      })
      .join("");
    legend.innerHTML = categoryChips;
    legend.querySelectorAll(".legend-chip[data-key]").forEach((chip) => {
      chip.addEventListener("click", () => {
        const key = chip.dataset.key;
        if (activeCategories.has(key)) activeCategories.delete(key);
        else activeCategories.add(key);
        renderAggregateSummary();
        drawMarkers();
      });
    });
    return;
  }
  const scopeLabel = datasetMode === "allIndia" ? "all-India infrastructure" : VIEW_MODES[viewMode].label.toLowerCase();
  legend.innerHTML = `<div class="legend-note">Bubble color reflects each ${level === "state" ? "state" : "city"}; bubble size reflects total ${scopeLabel} across selected categories.</div>`;
}

// ---- location table ----
// All-India city rows are grouped under a state band so every city in a state
// reads as one block; the state name and the city name are the two frozen
// columns on the left, category counts scroll horizontally underneath.
function renderTable(level) {
  renderLegend();
  const container = document.getElementById("location-table");
  const series = countableSeries();
  container.style.setProperty("--col-count", series.length);
  const grouped = datasetMode === "allIndia" && level === "city";
  container.classList.toggle("location-table--grouped", grouped);

  const head =
    `<div class="table-row table-head">` +
    (grouped ? `<span>State</span><span>City</span>` : `<span>${datasetMode === "allIndia" || level === "state" ? "State" : "City"}</span>`) +
    series.map((s) => `<span${activeCategories.has(s.key) ? "" : ' class="col-off"'}>${s.label}</span>`).join("") +
    `<span>Selected total</span></div>`;

  const cellsFor = (row) =>
    series
      .map((s) => `<span${activeCategories.has(s.key) ? "" : ' class="col-off"'}>${format.format(getRowValue(row, s.key))}</span>`)
      .join("");

  let body;
  if (grouped) {
    const byState = new Map();
    allIndiaCities.forEach((row) => {
      if (!byState.has(row.state)) byState.set(row.state, []);
      byState.get(row.state).push(row);
    });
    body = [...byState.entries()]
      .sort((a, b) => a[0].localeCompare(b[0]))
      .map(([state, rows]) => {
        const sorted = rows.slice().sort((a, b) => b.total - a.total || a.city.localeCompare(b.city));
        const band =
          `<div class="table-row table-band"><span>${state}</span>` +
          `<span>${format.format(sorted.length)} ${sorted.length === 1 ? "city" : "cities"}</span>` +
          series.map(() => `<span></span>`).join("") +
          `<span class="row-total">${format.format(sorted.reduce((t, r) => t + locationTotal(r), 0))}</span></div>`;
        return band + sorted
          .map((row) =>
            `<div class="table-row table-row--child"><span class="cell-state">${state}</span>` +
            `<span>${row.city}</span>${cellsFor(row)}` +
            `<span class="row-total">${format.format(locationTotal(row))}</span></div>`)
          .join("");
      })
      .join("");
  } else {
    const rows = rowsForLevel(level);
    const isStateLabel = datasetMode === "allIndia" || level === "state";
    body = rows
      .slice()
      .sort((a, b) => (a.levelName || a.city || a.state).localeCompare(b.levelName || b.city || b.state))
      .map(
        (row) =>
          `<div class="table-row"><span>${isStateLabel ? row.state : row.city}</span>${cellsFor(row)}` +
          `<span class="row-total">${format.format(locationTotal(row))}</span></div>`
      )
      .join("");
  }

  container.innerHTML = coverageNoteHtml(level) + head + body;
}

// Says out loud how much of the layer could be placed on a city row, so a
// missing city never looks like a missing facility.
function coverageNoteHtml(level) {
  if (datasetMode !== "allIndia" || level !== "city" || !allIndiaCoverage) return "";
  const c = allIndiaCoverage;
  return `<p class="table-note">${format.format(c.cities)} cities across ${format.format(c.states)} states/UTs.
    ${format.format(c.cityAttributed)} of ${format.format(c.totalPoints)} points carry a city;
    ${format.format(c.cityMissing)} do not and appear only in the state view and on the map.
    City is parsed from free-text postal addresses, so only cities named in the source extracts appear here.</p>`;
}

// ---- controls ----
// "Follow zoom" is a mode, not a level: with it on, the level buttons show
// which level the current zoom resolves to but do not pin it. Clicking a level
// pins that level and switches the mode off.
const followZoomToggle = document.getElementById("follow-zoom-toggle");

function syncLevelButtons() {
  const active = safeLevel();
  document.querySelectorAll(".level-button").forEach((b) => {
    b.classList.toggle("active", b.dataset.level === active);
    b.classList.toggle("level-button--auto", forcedLevel === "auto");
  });
}

document.querySelectorAll(".level-button").forEach((button) => {
  button.addEventListener("click", () => {
    forcedLevel = button.dataset.level;
    if (followZoomToggle) followZoomToggle.checked = false;
    syncLevelButtons();
    drawMarkers();
  });
});

if (followZoomToggle) {
  followZoomToggle.addEventListener("change", () => {
    if (followZoomToggle.checked) forcedLevel = "auto";
    syncLevelButtons();
    drawMarkers();
  });
}

document.querySelectorAll(".mode-button").forEach((button) => {
  button.addEventListener("click", () => {
    viewMode = button.dataset.mode;
    resetActiveCategories();
    document.querySelectorAll(".mode-button").forEach((b) => b.classList.toggle("active", b === button));
    renderAggregateSummary();
    drawMarkers();
  });
});

document.querySelectorAll(".dataset-button").forEach((button) => {
  button.addEventListener("click", () => {
    datasetMode = button.dataset.dataset;
    document.querySelectorAll(".dataset-button").forEach((b) => b.classList.toggle("active", b === button));
    document.body.classList.toggle("all-india-mode", datasetMode === "allIndia");
    resetActiveCategories();
    renderAggregateSummary();
    drawMarkers();
  });
});

map.on("zoomend moveend", () => {
  syncLevelButtons();
  drawMarkers();
});

const trueCoordsToggle = document.getElementById("true-coords-toggle");
if (trueCoordsToggle) {
  trueCoordsToggle.addEventListener("change", () => {
    trueCoordsOnly = trueCoordsToggle.checked;
    renderAggregateSummary();
    drawMarkers();
  });
}

const GRANULAR_KEYS = ["goethe_schools", "heis_german", "exam_centres", "pdot_siics",
                       "iiscs", "health_facilities", "medical_colleges", "nursing_colleges"];

// City is the only location field every pilot point carries. NABH rows in
// particular have state: null for all 3,847 of them, and the rows that do carry
// a state spell it inconsistently ("Tamilnadu", "Delhi (NCT)"). So the state a
// point belongs to is resolved from its city via cities.json, which is the one
// authoritative city -> state mapping, rather than trusted from the point.
let cityToState = new Map();

function stateForPoint(p) {
  return cityToState.get(p.city) || null;
}

// The pilot counts are RECOMPUTED from the points that actually render, rather
// than read from the stored columns in cities.json / states.json. The stored
// columns came from the consolidated table and disagreed with the map in a
// dozen small ways (de-duplicated rows, ungeocoded rows, NABH rows we now drop
// as corridor-ineligible). Deriving them means the card, the table and the dots
// are three views of one number and cannot drift apart.
//
// `labelFor` maps a point to the row it belongs to, so city rows key on the
// city and state rows key on the resolved state.
function recountFromPoints(rows, labelKey, labelFor, points) {
  const byLabel = new Map(rows.map((r) => [r[labelKey], { ...r }]));
  byLabel.forEach((row) => GRANULAR_KEYS.forEach((k) => (row[k] = 0)));
  points.forEach((p) => {
    const row = byLabel.get(labelFor(p));
    if (!row) return; // e.g. the two telc centres in Noida, outside the 15 cities
    const meta = POINT_SUBTYPE_META[p.subtype];
    if (meta && row[meta.fullKey] !== undefined) row[meta.fullKey] += 1;
  });
  return [...byLabel.values()];
}

const RENDERABLE_STATUSES = new Set(["source", "pin_centroid", "researched_override"]);

function isRenderableInfra(point) {
  // "duplicate_collapsed" and "undefined_flagged" stay in the data but off the map.
  return (
    RENDERABLE_STATUSES.has(point.coordinateStatus) &&
    Number.isFinite(point.latitude) &&
    Number.isFinite(point.longitude) &&
    !(point.latitude === 0 && point.longitude === 0)
  );
}

Promise.all([
  fetch("../data/cities.json").then((r) => r.json()),
  fetch("../data/states.json").then((r) => r.json()),
  fetch("../data/infrastructure-cleaned.json").then((r) => r.json()),
  fetch("../data/all-india-states.json").then((r) => r.json()),
  fetch("../data/all-india-cities.json").then((r) => r.json()),
  fetch("../data/all-india-coverage.json").then((r) => r.json()),
  // The RESOLVED point file, not the two raw layers: this one has
  // data/manual-overrides.json applied, so hand-corrected coordinates reach
  // the map and not just the tables. Written by prep/build_all_india_rollups.py.
  fetch("../data/all-india-points.json").then((r) => r.json()),
])
  .then(([cityRows, stateRows, infraRows, allIndiaStateRows, allIndiaCityRows, coverage, allIndiaPointRows]) => {
    cities = cityRows;
    states = stateRows;
    infrastructure = infraRows;
    allIndiaStates = allIndiaStateRows;
    allIndiaCities = allIndiaCityRows;
    allIndiaCoverage = coverage;
    allIndiaPoints = allIndiaPointRows.filter(isRenderableInfra);
    renderableInfrastructure = infrastructure.filter(isRenderableInfra).filter(isEligiblePilotPoint);
    cityToState = new Map(cities.map((c) => [c.city, c.state]));
    cities = recountFromPoints(cities, "city", (p) => p.city, renderableInfrastructure);
    states = recountFromPoints(states, "state", stateForPoint, renderableInfrastructure);
    cityColorScale = d3.scaleOrdinal().domain(cities.map((c) => c.city)).range(CITY_PALETTE);
    stateColorScale = d3.scaleOrdinal().domain(states.map((s) => s.state)).range(CITY_PALETTE);
    allIndiaStateColorScale = d3.scaleOrdinal().domain(allIndiaStates.map((s) => s.state)).range(CITY_PALETTE);
    console.info(
      `[infrastructure-layer] renderable=${renderableInfrastructure.length} dropped=${infrastructure.length - renderableInfrastructure.length} total=${infrastructure.length}`
    );
    resetActiveCategories();
    renderAggregateSummary();
    syncLevelButtons();
    drawMarkers();
  })
  .catch((error) => {
    document.getElementById("location-table").innerHTML = `<p class="detail-copy">Data load failed: ${error.message}</p>`;
  });
