import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  // The launchers and browser tests open the workbench at 127.0.0.1. Next.js 16.3+
  // blocks dev-server resources (including hot reload) for origins it was not told
  // about, which leaves every page stuck on its loading state.
  allowedDevOrigins: ["127.0.0.1"],
};

export default nextConfig;
