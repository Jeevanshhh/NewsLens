import type { DistEntry } from "../api/types";

/**
 * "By location" coverage map for the Analytics workspace.
 *
 * HONESTY NOTES (this is deliberately not a decorative globe):
 * - The only geographic signal the backend actually stores is a free-text
 *   `state` on each article (Indian states/UTs the rule classifier detects).
 *   There is no per-article coordinate and no country centroid in the data.
 * - We therefore plot ONLY the states that really appear in the analytics, at
 *   their *factual* real-world centroid (public geography - see STATE_CENTROIDS
 *   below), and size each marker by the *real* article count. We never invent a
 *   location, drop a marker for a state that has no articles, or fake a global
 *   spread when the coverage is regional.
 * - Projection auto-frames the real points so relative positions stay true.
 *   When there is no resolvable location we show a neutral, explanatory state
 *   instead of an empty/fabricated map.
 *
 * Rendering is a self-contained SVG (no map library / large dependency), it is
 * keyboard-/screen-reader-reachable via a hidden data table, and it never
 * encodes meaning through colour alone (size + text label + table).
 */

// Real approximate centroids (lon, lat) for the Indian states/UTs the backend's
// classifier can emit (see domain_config.INDIAN_STATES). These are public
// geographic reference values, NOT per-article data.
const STATE_CENTROIDS: Record<string, [number, number]> = {
  Delhi: [77.21, 28.61],
  Punjab: [75.71, 31.15],
  Haryana: [76.09, 29.06],
  Rajasthan: [73.02, 26.91],
  Bihar: [85.31, 25.61],
  Jharkhand: [85.28, 23.61],
  "Uttar Pradesh": [80.64, 26.85],
  "Madhya Pradesh": [78.66, 22.97],
  Maharashtra: [74.27, 19.75],
  Gujarat: [71.19, 23.02],
  "West Bengal": [87.85, 22.99],
  Odisha: [84.41, 20.95],
  Assam: [92.94, 26.2],
  Telangana: [78.49, 18.11],
  "Andhra Pradesh": [79.74, 15.91],
  "Tamil Nadu": [79.0, 11.13],
  Karnataka: [76.58, 15.32],
  Kerala: [76.27, 10.85],
};

interface PlottedLocation {
  name: string;
  count: number;
  lon: number;
  lat: number;
}

function toPlotted(data: DistEntry[]): PlottedLocation[] {
  const out: PlottedLocation[] = [];
  for (const entry of data) {
    const key = (entry.key ?? "").trim();
    const lowered = key.toLowerCase();
    if (!key || lowered === "unknown" || lowered === "other" || lowered === "n/a") continue;
    const centroid = STATE_CENTROIDS[key] ?? STATE_CENTROIDS[titleCase(key)];
    if (!centroid) continue; // No real coordinate -> do NOT guess one.
    out.push({ name: titleCase(key), count: entry.count, lon: centroid[0], lat: centroid[1] });
  }
  // Stable order (largest first) so the projection + labels are deterministic.
  return out.sort((a, b) => b.count - a.count || a.name.localeCompare(b.name));
}

function titleCase(s: string): string {
  return s.replace(/\w\S*/g, (w) => w[0].toUpperCase() + w.slice(1).toLowerCase());
}

// A small, fixed padding so single-point or clustered data still frames nicely.
const W = 720;
const H = 460;
const PAD = 56;

export default function LocationMap({ data }: { data: DistEntry[] }) {
  const points = toPlotted(data);

  if (points.length === 0) {
    return (
      <div className="locmap-empty" role="note">
        <div className="locmap-empty-glyph" aria-hidden>
          🗺️
        </div>
        <p className="muted">
          Location data is limited. Markers appear only for regions that publishers
          actually reported an article from - we never fabricate geographic coverage.
        </p>
      </div>
    );
  }

  // Fit an equirectangular frame around the real points (keeps relative geography true).
  const lons = points.map((p) => p.lon);
  const lats = points.map((p) => p.lat);
  let minLon = Math.min(...lons);
  let maxLon = Math.max(...lons);
  let minLat = Math.min(...lats);
  let maxLat = Math.max(...lats);
  // Guarantee a minimum span so a tight cluster isn't blown up to full screen.
  const minSpan = 8; // ~8 degrees
  if (maxLon - minLon < minSpan) {
    const mid = (minLon + maxLon) / 2;
    minLon = mid - minSpan / 2;
    maxLon = mid + minSpan / 2;
  }
  if (maxLat - minLat < minSpan) {
    const mid = (minLat + maxLat) / 2;
    minLat = mid - minSpan / 2;
    maxLat = mid + minSpan / 2;
  }
  // 10% breathing room around the frame.
  const padLon = (maxLon - minLon) * 0.1;
  const padLat = (maxLat - minLat) * 0.1;
  minLon -= padLon;
  maxLon += padLon;
  minLat -= padLat;
  maxLat += padLat;

  const projectX = (lon: number) => PAD + ((lon - minLon) / (maxLon - minLon)) * (W - 2 * PAD);
  const projectY = (lat: number) => PAD + ((maxLat - lat) / (maxLat - minLat)) * (H - 2 * PAD);

  const maxCount = Math.max(...points.map((p) => p.count), 1);
  const radiusFor = (count: number) => 6 + Math.sqrt(count / maxCount) * 22;

  // Build a handful of evenly spaced graticule lines within the frame.
  const gridLon = gridValues(minLon, maxLon, 5);
  const gridLat = gridValues(minLat, maxLat, 5);

  return (
    <div className="locmap">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        preserveAspectRatio="xMidYMid meet"
        role="img"
        aria-label={`Location coverage map showing ${points.length} region${
          points.length === 1 ? "" : "s"
        }. See the adjacent list for exact counts.`}
        className="locmap-svg"
      >
        <rect
          x={PAD - 16}
          y={PAD - 16}
          width={W - 2 * (PAD - 16)}
          height={H - 2 * (PAD - 16)}
          rx={14}
          className="locmap-frame"
        />
        {gridLon.map((lon) => (
          <line
            key={`vx${lon.toFixed(2)}`}
            x1={projectX(lon)}
            y1={PAD - 16}
            x2={projectX(lon)}
            y2={H - PAD + 16}
            className="locmap-grid"
          />
        ))}
        {gridLat.map((lat) => (
          <line
            key={`hz${lat.toFixed(2)}`}
            x1={PAD - 16}
            y1={projectY(lat)}
            x2={W - PAD + 16}
            y2={projectY(lat)}
            className="locmap-grid"
          />
        ))}
        {points.map((p) => {
          const cx = projectX(p.lon);
          const cy = projectY(p.lat);
          const r = radiusFor(p.count);
          return (
            <g key={p.name} className="locmap-point">
              <circle cx={cx} cy={cy} r={r} className="locmap-bubble" />
              <circle cx={cx} cy={cy} r={Math.min(r, 4)} className="locmap-core" />
              <text x={cx} y={cy - r - 6} textAnchor="middle" className="locmap-label">
                {p.name}
              </text>
              <text x={cx} y={cy - r + 6} textAnchor="middle" className="locmap-count">
                {p.count}
              </text>
              <title>{`${p.name}: ${p.count} article${p.count === 1 ? "" : "s"}`}</title>
            </g>
          );
        })}
      </svg>

      {/* Accessible, non-visual representation - never rely on colour/position alone. */}
      <table className="locmap-table">
        <caption>Coverage by location (article counts)</caption>
        <thead>
          <tr>
            <th scope="col">Location</th>
            <th scope="col">Articles</th>
          </tr>
        </thead>
        <tbody>
          {points.map((p) => (
            <tr key={p.name}>
              <th scope="row">{p.name}</th>
              <td>{p.count}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// Evenly-spaced, "nice" round values between lo and hi (approx `count` of them).
function gridValues(lo: number, hi: number, count: number): number[] {
  const step = (hi - lo) / (count + 1);
  const out: number[] = [];
  for (let i = 1; i <= count; i++) out.push(lo + step * i);
  return out;
}
