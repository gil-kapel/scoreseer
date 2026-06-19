import { NextResponse } from "next/server";

import { API_BASE, backendHeaders } from "@/lib/backend";

// Server-side proxy: the browser POSTs here, we forward to the backend (adding
// the API key). Keeps the API base + key server-side and avoids CORS.
export async function POST(req: Request) {
  const body = await req.json().catch(() => ({}));
  const res = await fetch(`${API_BASE}/api/admin/runs`, {
    method: "POST",
    headers: backendHeaders({ "content-type": "application/json" }),
    body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  return NextResponse.json(data, { status: res.status });
}
