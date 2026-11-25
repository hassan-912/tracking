import { NextResponse, type NextRequest } from "next/server";
import { SESSION_COOKIE, validSession } from "@/lib/session";

// Everything needs the office password, except the sign-in page itself.
export async function proxy(request: NextRequest) {
  if (await validSession(request.cookies.get(SESSION_COOKIE)?.value)) {
    return NextResponse.next();
  }
  if (request.nextUrl.pathname.startsWith("/api/")) {
    return NextResponse.json({ error: "Please sign in" }, { status: 401 });
  }
  return NextResponse.redirect(new URL("/login", request.url));
}

export const config = {
  matcher: ["/((?!login|api/login|api/agent|_next/static|_next/image|favicon.ico).*)"],
};
