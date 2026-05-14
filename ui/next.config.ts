import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";

const withNextIntl = createNextIntlPlugin("./src/i18n/request.ts");

const nextConfig: NextConfig = {
  async rewrites() {
    const metadataTarget = process.env.METADATA_SVC_URL ?? "http://localhost:8001";
    const dataTarget = process.env.DATA_SVC_URL ?? "http://localhost:8002";
    const navigationTarget = process.env.NAV_SVC_URL ?? "http://localhost:8003";
    const queryTarget = process.env.QUERY_SVC_URL ?? "http://localhost:8004";

    return [
      { source: "/api/metadata/:path*", destination: `${metadataTarget}/:path*` },
      { source: "/api/data/:path*", destination: `${dataTarget}/:path*` },
      { source: "/api/navigation/:path*", destination: `${navigationTarget}/:path*` },
      { source: "/api/query/:path*", destination: `${queryTarget}/:path*` },
    ];
  },
};

export default withNextIntl(nextConfig);
