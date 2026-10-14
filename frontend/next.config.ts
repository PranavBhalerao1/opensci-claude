import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // The recorded swarm demo is a static page carried over from the original site (public/demo).
  async rewrites() {
    return [{ source: "/demo", destination: "/demo/index.html" }];
  },
};

export default nextConfig;
