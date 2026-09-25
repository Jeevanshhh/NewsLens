interface Props {
  page: number;
  pages: number;
  onChange: (page: number) => void;
}

export default function Pagination({ page, pages, onChange }: Props) {
  if (pages <= 1) return null;
  const hasPrev = page > 1;
  const hasNext = page < pages;

  return (
    <div className="pagination">
      <button className="btn small" disabled={!hasPrev} onClick={() => onChange(page - 1)}>
        ‹ Prev
      </button>
      <span className="muted">
        Page {page} of {pages}
      </span>
      <button className="btn small" disabled={!hasNext} onClick={() => onChange(page + 1)}>
        Next ›
      </button>
    </div>
  );
}
