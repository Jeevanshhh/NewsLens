import { useEffect, useRef, useState } from "react";

import { downloadExport } from "../api/client";
import type { ExportFormat } from "../api/types";

interface ExportParams {
  search_id?: number;
  provider?: string;
  category?: string;
  state?: string;
  q?: string;
  sort?: string;
}

const FORMATS: { id: ExportFormat; label: string }[] = [
  { id: "csv", label: "CSV" },
  { id: "xlsx", label: "Excel (.xlsx)" },
  { id: "pdf", label: "PDF" },
  { id: "docx", label: "Word (.docx)" },
];

export default function ExportMenu({ params }: { params: ExportParams }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState<ExportFormat | null>(null);
  const [error, setError] = useState<string | null>(null);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  const run = async (format: ExportFormat) => {
    setBusy(format);
    setError(null);
    try {
      await downloadExport({ ...params, format });
      setOpen(false);
    } catch {
      setError("Export failed");
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="menu-wrap" ref={ref}>
      <button className="btn" onClick={() => setOpen((o) => !o)}>
        Export ▾
      </button>
      {open && (
        <div className="menu">
          {FORMATS.map((f) => (
            <button
              key={f.id}
              className="menu-item"
              onClick={() => run(f.id)}
              disabled={busy !== null}
            >
              {busy === f.id ? <span className="spinner" /> : null}
              {f.label}
            </button>
          ))}
          {error && <div className="menu-sep" />}
          {error && <div className="menu-item" style={{ color: "var(--danger)" }}>{error}</div>}
        </div>
      )}
    </div>
  );
}
