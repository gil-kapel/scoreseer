import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // NOTE: do NOT set `output: "standalone"` — it breaks Vercel's serverless
  // runtime (ReferenceError: __dirname). The Docker prod image runs `next start`
  // instead (see frontend/Dockerfile), so standalone isn't needed anywhere.
};

export default nextConfig;
