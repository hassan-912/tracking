import { NextResponse } from "next/server";
import { agentDenied } from "@/lib/agent";
import { categoryOf, cleanRef } from "@/lib/categories";
import { ensureSchema, sql } from "@/lib/db";
import { decrypt, encrypt } from "@/lib/secure";

// Used only by the office PC helper (office_helper.py), with its AGENT_TOKEN.
//   POST /api/agent/claim   {host}  -> next queued run + its clients (heartbeat too)
//   POST /api/agent/import  {category, clients: [{name, ref, secret, notes}], replace}
export async function POST(request: Request, ctx: RouteContext<"/api/agent/[action]">) {
  const denied = agentDenied(request);
  if (denied) return denied;
  await ensureSchema();
  const { action } = await ctx.params;
  const body = await request.json().catch(() => ({}));
  const db = sql();

  if (action === "claim") {
    await db`INSERT INTO agent (id, host, last_seen) VALUES (1, ${String(body.host ?? "")}, now())
             ON CONFLICT (id) DO UPDATE SET host = EXCLUDED.host, last_seen = now()`;
    const jobs = (await db`UPDATE jobs SET state = 'running', started_at = now()
        WHERE id = (SELECT id FROM jobs WHERE state = 'queued' ORDER BY id LIMIT 1)
          AND state = 'queued'
        RETURNING id, category, client_ids`) as
      { id: number; category: string; client_ids: number[] | null }[];
    const job = jobs[0];
    if (!job) return NextResponse.json({ job: null });
    const rows = (job.client_ids
      ? await db`SELECT id, name, ref, secret_enc FROM clients
                 WHERE category = ${job.category} AND id = ANY(${job.client_ids}) ORDER BY id`
      : await db`SELECT id, name, ref, secret_enc FROM clients
                 WHERE category = ${job.category} ORDER BY id`) as
      { id: number; name: string; ref: string; secret_enc: string }[];
    return NextResponse.json({
      job: { id: job.id, category: job.category },
      clients: rows.map((r) => ({ id: r.id, name: r.name, ref: r.ref, secret: decrypt(r.secret_enc) })),
    });
  }

  if (action === "import") {
    const cat = categoryOf(body.category);
    if (!cat || !Array.isArray(body.clients)) {
      return NextResponse.json({ error: "Need category and clients" }, { status: 400 });
    }
    const existing = (await db`SELECT COUNT(*)::int AS n FROM clients WHERE category = ${cat.key}`) as { n: number }[];
    if (existing[0].n && !body.replace) {
      return NextResponse.json({ skipped: true, existing: existing[0].n });
    }
    if (body.replace) await db`DELETE FROM clients WHERE category = ${cat.key}`;
    for (const c of body.clients) {
      await db`INSERT INTO clients (category, name, ref, secret_enc, notes) VALUES
        (${cat.key}, ${String(c.name ?? "")}, ${cleanRef(cat, String(c.ref ?? ""))},
         ${encrypt(String(c.secret ?? ""))}, ${String(c.notes ?? "")})`;
    }
    return NextResponse.json({ imported: body.clients.length });
  }

  return NextResponse.json({ error: "Unknown action" }, { status: 404 });
}
