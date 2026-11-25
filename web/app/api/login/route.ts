import { NextResponse } from "next/server";
import { passwordMatches } from "@/lib/secure";
import { makeSession, SESSION_COOKIE, SESSION_DAYS } from "@/lib/session";

export async function POST(request: Request) {
  const { password } = (await request.json().catch(() => ({}))) as { password?: string };
  if (!password || !passwordMatches(password)) {
    await new Promise((r) => setTimeout(r, 800)); // slow down guessing
    return NextResponse.json({ error: "Wrong password" }, { status: 401 });
  }
  const res = NextResponse.json({ ok: true });
  res.cookies.set(SESSION_COOKIE, await makeSession(), {
    httpOnly: true, secure: true, sameSite: "lax", path: "/", maxAge: SESSION_DAYS * 86_400,
  });
  return res;
}

export async function DELETE() {
  const res = NextResponse.json({ ok: true });
  res.cookies.delete(SESSION_COOKIE);
  return res;
}
