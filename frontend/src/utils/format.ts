// Small formatting helpers shared across the UI.

// Decode HTML entities (e.g. "&nbsp;", "&amp;", "&#39;") that some feeds
// still leak through. Defensive: the backend now cleans these too.
export function decodeHtmlEntities(value: string | null | undefined): string {
  if (!value) return "";
  const el = document.createElement("textarea");
  el.innerHTML = value;
  return el.value.replace(/\u00a0/g, " ").trim();
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

// "2 hours ago" style relative time, falling back to a short date.
export function relativeTime(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const diff = Date.now() - d.getTime();
  const sec = Math.round(diff / 1000);
  if (sec < 60) return "just now";
  const min = Math.round(sec / 60);
  if (min < 60) return `${min} min ago`;
  const hr = Math.round(min / 60);
  if (hr < 24) return `${hr} hour${hr === 1 ? "" : "s"} ago`;
  const day = Math.round(hr / 24);
  if (day < 30) return `${day} day${day === 1 ? "" : "s"} ago`;
  return d.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export function titleCase(value: string | null | undefined): string {
  if (!value) return "—";
  return value
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

// A value is "meaningful" for display when it isn't empty or one of the
// rule-based classifier's neutral placeholders.
export function isMeaningful(value: string | null | undefined): boolean {
  if (!value) return false;
  const v = value.trim().toLowerCase();
  return v !== "" && v !== "unknown" && v !== "other" && v !== "n/a" && v !== "none";
}
