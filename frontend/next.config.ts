import type { NextConfig } from "next";

// Next.js dev server blocks cross-origin requests (including the HMR
// websocket) from any host not in this list, to guard against DNS
// rebinding. Set NEXT_ALLOWED_DEV_ORIGINS (comma-separated hostnames, no
// protocol/port) to access the dev server from a LAN IP or custom hostname.
const allowedDevOrigins = process.env.NEXT_ALLOWED_DEV_ORIGINS
  ? process.env.NEXT_ALLOWED_DEV_ORIGINS.split(",").map((s) => s.trim()).filter(Boolean)
  : undefined;

const nextConfig: NextConfig = {
  // Enable standalone output for optimized Docker deployment
  output: "standalone",

  ...(allowedDevOrigins && allowedDevOrigins.length > 0 ? { allowedDevOrigins } : {}),

  // Experimental features
  // Type assertion needed: proxyClientMaxBodySize is valid in Next.js 15 but types lag behind
  experimental: {
    // Proxy body size limit for file uploads through the /api/* rewrite
    // proxy to FastAPI. Next.js requires a finite value here, so the
    // proxied path is capped at FRONTEND_PROXY_MAX_BODY_SIZE (default
    // 10gb, effectively any PDF). The direct API path (the default upload
    // route, straight to port 5055) has no cap at all.
    proxyClientMaxBodySize: process.env.FRONTEND_PROXY_MAX_BODY_SIZE || '10gb',
    // Local CPU inference (Studio generation, chat) can take several minutes
    proxyTimeout: 900000,
  } as NextConfig['experimental'],

  // API Rewrites: Proxy /api/* requests to FastAPI backend
  // This simplifies reverse proxy configuration - users only need to proxy to port 8502
  // Next.js handles internal routing to the API backend on port 5055
  async rewrites() {
    // INTERNAL_API_URL: Where Next.js server-side should proxy API requests
    // Default: http://localhost:5055 (single-container deployment)
    // Override for multi-container: INTERNAL_API_URL=http://api-service:5055
    const internalApiUrl = process.env.INTERNAL_API_URL || 'http://localhost:5055'

    console.log(`[Next.js Rewrites] Proxying /api/* to ${internalApiUrl}/api/*`)

    return [
      {
        source: '/api/:path*',
        destination: `${internalApiUrl}/api/:path*`,
      },
      {
        source: '/f/:path*',
        destination: `${internalApiUrl}/f/:path*`,
      },
    ]
  },

  // Redirect the legacy credentials route to the canonical "Models" route so
  // existing bookmarks and links keep working.
  async redirects() {
    return [
      {
        source: '/settings/api-keys',
        destination: '/settings/models',
        permanent: true,
      },
    ]
  },
};

export default nextConfig;
