"use client";

import { Button } from "@/components/ui/button";

/** Numbered pagination over a server-side total. Pages are 1-based. */
export function DataPagination({
  page,
  totalPages,
  totalItems,
  onChange,
}: {
  page: number;
  totalPages: number;
  totalItems: number;
  onChange: (page: number) => void;
}) {
  if (totalPages <= 1 && totalItems === 0) return null;

  // Windowed page numbers: first, last, and neighbours of the current page.
  const numbers: (number | "…")[] = [];
  for (let p = 1; p <= totalPages; p++) {
    if (p === 1 || p === totalPages || Math.abs(p - page) <= 1) {
      numbers.push(p);
    } else if (numbers[numbers.length - 1] !== "…") {
      numbers.push("…");
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
      <p className="text-sm text-muted-foreground" aria-live="polite">
        Page {Math.min(page, Math.max(totalPages, 1))} of{" "}
        {Math.max(totalPages, 1)} · {totalItems} item
        {totalItems === 1 ? "" : "s"}
      </p>
      {totalPages > 1 && (
        <nav
          aria-label="Pagination"
          className="flex items-center gap-1"
        >
          <Button
            size="sm"
            variant="outline"
            disabled={page <= 1}
            onClick={() => onChange(page - 1)}
            aria-label="Previous page"
          >
            ← Prev
          </Button>
          {numbers.map((n, i) =>
            n === "…" ? (
              <span
                key={`gap-${i}`}
                className="px-1 text-sm text-muted-foreground"
                aria-hidden
              >
                …
              </span>
            ) : (
              <Button
                key={n}
                size="sm"
                variant={n === page ? "default" : "ghost"}
                onClick={() => onChange(n)}
                aria-label={`Page ${n}`}
                aria-current={n === page ? "page" : undefined}
              >
                {n}
              </Button>
            ),
          )}
          <Button
            size="sm"
            variant="outline"
            disabled={page >= totalPages}
            onClick={() => onChange(page + 1)}
            aria-label="Next page"
          >
            Next →
          </Button>
        </nav>
      )}
    </div>
  );
}
