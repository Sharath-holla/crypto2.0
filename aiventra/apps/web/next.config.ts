import type { NextConfig } from "next";
const config: NextConfig = {
  // Disposable browser servers must not share the owner's running dev lock.
  distDir:
    process.env.AIVENTRA_TEST_BUILD === "crypto"
      ? ".next-crypto"
      : process.env.AIVENTRA_TEST_BUILD === "browser"
        ? ".next-browser"
        : process.env.AIVENTRA_TEST_BUILD === "delivery"
          ? ".next-delivery"
          : process.env.AIVENTRA_TEST_BUILD === "production"
            ? ".next-build"
            : ".next",
  output: "standalone",
  poweredByHeader: false,
  devIndicators: false,
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "same-origin" },
        ],
      },
    ];
  },
};
export default config;
