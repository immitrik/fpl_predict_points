// Local stand-in for the Cloudflare Worker (worker/fpl-proxy.js), for testing the planner.
// Usage: node scripts/dev-proxy.mjs   then open  http://localhost:4173/?t=<id>&proxy=<encoded http://localhost:8787/?u={url}>#planner
import http from "node:http";

http
  .createServer(async (req, res) => {
    const target = new URL(req.url, "http://x").searchParams.get("u") ?? "";
    res.setHeader("Access-Control-Allow-Origin", "*");
    if (!target.startsWith("https://fantasy.premierleague.com/api/")) {
      res.statusCode = 403;
      return res.end("forbidden");
    }
    const up = await fetch(target, { headers: { "User-Agent": "Mozilla/5.0" } });
    res.statusCode = up.status;
    res.setHeader("Content-Type", "application/json");
    res.end(Buffer.from(await up.arrayBuffer()));
  })
  .listen(8787, () => console.log("proxy on :8787"));
