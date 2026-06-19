import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Emit a self-contained server bundle (.next/standalone) for the prod Docker image.
  output: "standalone",
};

export default nextConfig;
