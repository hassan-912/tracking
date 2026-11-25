"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { CATEGORIES } from "@/lib/categories";

export default function Home() {
  const [counts, setCounts] = useState<Record<string, number> | null>(null);

  useEffect(() => {
    fetch("/api/clients").then((r) => (r.ok ? r.json() : null)).then(setCounts);
  }, []);

  return (
    <>
      <h1>Visa tracking</h1>
      <p className="muted">Choose what you want to do.</p>
      <div className="choices">
        <Link href="/tracking" className="choice primary-choice">
          <span className="choice-title">Tracking</span>
          <span>Check application statuses and get the screenshots PDF.</span>
        </Link>
        <Link href="/data" className="choice">
          <span className="choice-title">Data entry</span>
          <span>Add, edit or remove clients for each site.</span>
        </Link>
      </div>
      <h2 className="small-heading">Clients in the website</h2>
      <div className="stats">
        {CATEGORIES.map((c) => (
          <div key={c.key} className="stat">
            <span className="muted">{c.title}</span>
            <strong>{counts ? counts[c.key] ?? 0 : "…"}</strong>
          </div>
        ))}
      </div>
    </>
  );
}
