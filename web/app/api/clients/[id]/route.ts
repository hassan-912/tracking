import { NextResponse } from "next/server";
import { categoryOf, cleanRef } from "@/lib/categories";
import { ensureSchema, sql } from "@/lib/db";
import { encrypt } from "@/lib/secure";

// PATCH /api/clients/12  {name, ref, secret, notes}
export async function PATCH(request: Request, ctx: RouteContext<"/api/clients/[id]">) {
  await ensureSchema();
  const id = Number((await ctx.params).id);
  const body = await request.json();
  const db = sql();
  const found = (await db`SELECT category FROM clients WHERE id = ${id}`) as { category: string }[];
  const cat = categoryOf(found[0]?.category ?? null);
  if (!cat) return NextResponse.json({ error: "Client not found" }, { status: 404 });
  await db`UPDATE clients SET
      name = ${String(body.name ?? "").trim()},
      ref = ${cleanRef(cat, String(body.ref ?? ""))},
      secret_enc = ${encrypt(String(body.secret ?? "").trim())},
      notes = ${String(body.notes ?? "").trim()},
      updated_at = now()
    WHERE id = ${id}`;
  return NextResponse.json({ ok: true });
}

export async function DELETE(_request: Request, ctx: RouteContext<"/api/clients/[id]">) {
  await ensureSchema();
  await sql()`DELETE FROM clients WHERE id = ${Number((await ctx.params).id)}`;
  return NextResponse.json({ ok: true });
}
