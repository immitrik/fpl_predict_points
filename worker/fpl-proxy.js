// Minimal CORS proxy for the official FPL API, for a free Cloudflare Worker.
// Only FPL API URLs are proxied, and only for browsers on the allowed origins below.
// Deploy: either `cd worker && npx wrangler login && npx wrangler deploy`, or connect the repo to a Cloudflare Worker
// with Build settings -> Root directory = worker (the Worker name must match `name` in wrangler.toml).
// Then set the repository variable FPL_PROXY (Settings -> Secrets and variables -> Actions -> Variables) to
//   https://fpl-proxy.<your-subdomain>.workers.dev/?u={url}
// and re-run the "Update predictions and deploy" workflow.

const ALLOWED_ORIGINS = [
  "https://immitrik.github.io",
  "http://localhost:4173", // vite preview
  "http://localhost:5173", // vite dev
];

export default {
  async fetch(request) {
    const origin = request.headers.get("Origin") || "";
    const cors = {
      "Access-Control-Allow-Origin": ALLOWED_ORIGINS.includes(origin) ? origin : ALLOWED_ORIGINS[0],
      Vary: "Origin",
    };
    if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: cors });
    if (!ALLOWED_ORIGINS.includes(origin)) {
      return new Response("Origin not allowed", { status: 403, headers: cors });
    }
    const target = new URL(request.url).searchParams.get("u");
    if (!target || !target.startsWith("https://fantasy.premierleague.com/api/")) {
      return new Response("Only FPL API URLs are allowed", { status: 403, headers: cors });
    }
    const upstream = await fetch(target, {
      headers: { "User-Agent": "Mozilla/5.0 (fpl-predict-points proxy)" },
      cf: { cacheTtl: 60, cacheEverything: true },
    });
    return new Response(upstream.body, {
      status: upstream.status,
      headers: { ...cors, "Content-Type": "application/json" },
    });
  },
};
