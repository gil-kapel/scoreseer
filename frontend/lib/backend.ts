// Server-only helpers for talking to the FastAPI backend.
// API_TOKEN is injected as `x-api-key` on every call; it lives in the Next.js
// server env and is never sent to the browser.

export const API_BASE = process.env.API_BASE ?? "http://localhost:8000";

export function backendHeaders(extra?: Record<string, string>): Record<string, string> {
  const token = process.env.API_TOKEN;
  return {
    ...(token ? { "x-api-key": token } : {}),
    ...(extra ?? {}),
  };
}
