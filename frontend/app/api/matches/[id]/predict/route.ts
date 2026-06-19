import { NextResponse } from "next/server";

import { API_BASE, backendHeaders } from "@/lib/backend";

export async function POST(_req: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const res = await fetch(`${API_BASE}/api/matches/${id}/predict`, {
    method: "POST",
    headers: backendHeaders(),
  });
  const data = await res.json().catch(() => ({}));
  return NextResponse.json(data, { status: res.status });
}
