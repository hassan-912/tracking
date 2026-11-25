import { NextResponse } from "next/server";
import { categoryOf } from "@/lib/categories";
import { ensureSchema, sql } from "@/lib/db";

// GET /api/jobs -> the latest tracking run + whether the office PC helper is online
export async function GET() {
  await ensureSchema();
  const db = sql();
  const jobs = await db`SELECT id, category, state, windows, log, error, results,
      EXISTS (SELECT 1 FROM job_files f WHERE f.job_id = jobs.id AND f.kind = 'pdf') AS has_pdf,
      EXISTS (SELECT 1 FROM job_files f WHERE f.job_id = jobs.id AND f.kind = 'xlsx') AS has_xlsx,
      created_at, started_at, finished_at
    FROM jobs ORDER BY id DESC LIMIT 1`;
  const agent = (await db`SELECT host, last_seen,
      (last_seen > now() - interval '30 seconds') AS online FROM agent WHERE id = 1`) as
    { host: string; last_seen: string; online: boolean }[];
  return NextResponse.json({ job: jobs[0] ?? null, agent: agent[0] ?? null });
}

// POST /api/jobs {category, ids?} -> ask the office PC to check these clients
export async function POST(request: Request) {
  await ensureSchema();
  const body = await request.json();
  const cat = categoryOf(body.category);
  if (!cat) return NextResponse.json({ error: "Unknown site" }, { status: 400 });
  const ids: number[] | null = Array.isArray(body.ids) && body.ids.length
    ? body.ids.map(Number) : null;
  const db = sql();
  const busy = await db`SELECT id FROM jobs WHERE state IN ('queued', 'running', 'waiting')
                        AND created_at > now() - interval '3 hours' LIMIT 1`;
  if (busy.length) {
    return NextResponse.json({ error: "A tracking run is already going — wait for it to finish." },
                             { status: 409 });
  }
  const rows = (await db`INSERT INTO jobs (category, client_ids) VALUES (${cat.key}, ${ids})
                         RETURNING id`) as { id: number }[];
  return NextResponse.json({ id: rows[0].id });
}
