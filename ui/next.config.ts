import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";

const withNextIntl = createNextIntlPlugin("./src/i18n/request.ts");

const nextConfig: NextConfig = {
  async rewrites() {
    const coreTarget =
      process.env.CORE_SVC_URL ?? process.env.METADATA_SVC_URL ?? "http://localhost:8001";
    const queryTarget = process.env.QUERY_SVC_URL ?? "http://localhost:8004";

    return [
      { source: "/api/metadata/:path*", destination: `${coreTarget}/:path*` },
      { source: "/api/data/:path*", destination: `${coreTarget}/:path*` },
      { source: "/api/navigation/:path*", destination: `${coreTarget}/:path*` },
      { source: "/api/query/:path*", destination: `${queryTarget}/:path*` },
    ];
  },
};

export default withNextIntl(nextConfig);
