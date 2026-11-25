import { NextResponse } from "next/server";
import { categoryOf, cleanRef, CATEGORIES, problemOf } from "@/lib/categories";
import { ensureSchema, sql } from "@/lib/db";
import { decrypt, encrypt } from "@/lib/secure";

type Row = { id: number; name: string; ref: string; secret_enc: string; notes: string };

// GET /api/clients?category=vfs  -> that site's clients
// GET /api/clients               -> how many clients each site has
export async function GET(request: Request) {
  await ensureSchema();
  const db = sql();
  const key = new URL(request.url).searchParams.get("category");
  if (!key) {
    const rows = (await db`SELECT category, COUNT(*)::int AS n FROM clients GROUP BY category`) as
      { category: string; n: number }[];
    return NextResponse.json(Object.fromEntries(CATEGORIES.map((c) =>
      [c.key, rows.find((r) => r.category === c.key)?.n ?? 0])));
  }
  const cat = categoryOf(key);
  if (!cat) return NextResponse.json({ error: "Unknown site" }, { status: 400 });
  const rows = (await db`SELECT id, name, ref, secret_enc, notes FROM clients
                         WHERE category = ${cat.key} ORDER BY id`) as Row[];
  return NextResponse.json(rows.map((r) => {
    const secret = decrypt(r.secret_enc);
    return { id: r.id, name: r.name, ref: r.ref, secret, notes: r.notes,
             problem: problemOf(cat, r.ref, secret) };
  }));
}

// POST /api/clients  {category, name, ref, secret, notes}
export async function POST(request: Request) {
  await ensureSchema();
  const body = await request.json();
  const cat = categoryOf(body.category);
  if (!cat) return NextResponse.json({ error: "Unknown site" }, { status: 400 });
  const ref = cleanRef(cat, String(body.ref ?? ""));
  const secret = String(body.secret ?? "").trim();
  const rows = (await sql()`INSERT INTO clients (category, name, ref, secret_enc, notes)
    VALUES (${cat.key}, ${String(body.name ?? "").trim()}, ${ref}, ${encrypt(secret)},
            ${String(body.notes ?? "").trim()}) RETURNING id`) as { id: number }[];
  return NextResponse.json({ id: rows[0].id });
}
