// Minimal CORS proxy for the official FPL API, for a free Cloudflare Worker.
// Deploy: Cloudflare dashboard -> Workers & Pages -> Create -> paste this file -> Deploy.
// Then set the repository variable FPL_PROXY (Settings -> Secrets and variables -> Actions -> Variables) to
//   https://<your-worker>.workers.dev/?u={url}
// and re-run the "Update predictions and deploy" workflow. Only FPL API URLs are proxied.
export default {
  async fetch(request) {
    const target = new URL(request.url).searchParams.get("u");
    if (!target || !target.startsWith("https://fantasy.premierleague.com/api/")) {
      return new Response("Only FPL API URLs are allowed", { status: 403 });
    }
    const upstream = await fetch(target, {
      headers: { "User-Agent": "Mozilla/5.0 (fpl-predict-points proxy)" },
      cf: { cacheTtl: 60, cacheEverything: true },
    });
    return new Response(upstream.body, {
      status: upstream.status,
      headers: {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
      },
    });
  },
};
