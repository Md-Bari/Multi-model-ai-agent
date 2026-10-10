import { NextResponse, type NextRequest } from "next/server";

// Optimistic check only: the cookie's presence decides the redirect. The backend still
// verifies the session on every API call, and the app shell sends users to /login on 401.
const SESSION_COOKIE = "llmgw_session";
const PROTECTED = ["/dashboard", "/usage", "/keys", "/playground", "/docs"];
const AUTH_PAGES = ["/login", "/register"];

export function proxy(request: NextRequest) {
  const { pathname, search } = request.nextUrl;
  const hasSession = request.cookies.has(SESSION_COOKIE);

  if (!hasSession && PROTECTED.some((p) => pathname === p || pathname.startsWith(`${p}/`))) {
    const url = new URL("/login", request.url);
    url.searchParams.set("next", pathname + search);
    return NextResponse.redirect(url);
  }
  if (hasSession && AUTH_PAGES.includes(pathname)) {
    return NextResponse.redirect(new URL("/dashboard", request.url));
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/dashboard/:path*", "/usage/:path*", "/keys/:path*", "/playground/:path*", "/docs/:path*", "/login", "/register"],
};
