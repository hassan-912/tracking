"use client";

import { CATEGORIES, type CategoryKey } from "@/lib/categories";

export default function SiteTabs({ value, onChange, counts }: {
  value: CategoryKey;
  onChange: (key: CategoryKey) => void;
  counts?: Record<string, number>;
}) {
  return (
    <div className="tabs" role="tablist">
      {CATEGORIES.map((c) => (
        <button key={c.key} role="tab" aria-selected={value === c.key}
                className={value === c.key ? "tab active" : "tab"} onClick={() => onChange(c.key)}>
          {c.title}{counts ? ` (${counts[c.key] ?? 0})` : ""}
        </button>
      ))}
    </div>
  );
}
