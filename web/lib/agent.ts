import "server-only";
import { createHash, timingSafeEqual } from "node:crypto";
import { NextResponse } from "next/server";

/** The office PC helper signs its requests with AGENT_TOKEN (not the office password). */
export function agentDenied(request: Request): NextResponse | null {
  const expected = process.env.AGENT_TOKEN ?? "";
  const sent = (request.headers.get("authorization") ?? "").replace(/^Bearer\s+/i, "");
  const a = createHash("sha256").update(sent).digest();
  const b = createHash("sha256").update(expected).digest();
  if (!expected || !sent || !timingSafeEqual(a, b)) {
    return NextResponse.json({ error: "Not the office helper" }, { status: 401 });
  }
  return null;
}
