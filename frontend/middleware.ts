import { NextResponse, type NextRequest } from "next/server";

// Single-owner gate. When BASIC_AUTH_USER + BASIC_AUTH_PASSWORD are set, the whole
// app is behind HTTP Basic auth; when unset (local dev), it's wide open.
export function middleware(req: NextRequest) {
  const user = process.env.BASIC_AUTH_USER;
  const pass = process.env.BASIC_AUTH_PASSWORD;
  if (!user || !pass) return NextResponse.next();

  const header = req.headers.get("authorization");
  if (header?.startsWith("Basic ")) {
    const [u, p] = atob(header.slice(6)).split(":");
    if (u === user && p === pass) return NextResponse.next();
  }
  return new NextResponse("Authentication required", {
    status: 401,
    headers: { "WWW-Authenticate": 'Basic realm="ScoreSeer"' },
  });
}

export const config = {
  // Gate everything except Next internals + the favicon.
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
