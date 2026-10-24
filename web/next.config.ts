import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  agentRules: false,
  // The home directory holds a stray package-lock.json that Next would take for the root.
  turbopack: { root: process.cwd() },
  images: {
    // Listing photos come from six source sites and their CDNs; they are shown as-is.
    unoptimized: true,
  },
};

export default nextConfig;
