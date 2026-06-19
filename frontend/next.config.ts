import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Standalone server bundle for the Docker prod image only. On Vercel, let Vercel
  // build/run it — `output: standalone` breaks Vercel's serverless runtime
  // (ReferenceError: __dirname). Vercel sets process.env.VERCEL=1.
  output: process.env.VERCEL ? undefined : "standalone",
};

export default nextConfig;
