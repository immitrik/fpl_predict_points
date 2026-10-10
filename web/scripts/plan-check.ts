// Dev check: load a real team, estimate selling prices, run the transfer optimiser.
// Usage: node scripts/plan-check.ts <teamId> [freeTransfers]
import { readFileSync } from "node:fs";
import highsLoader from "highs";
import { loadTeam, sellingPrices } from "../src/fplApi.ts";
import { planTransfers, type Candidate } from "../src/optimizer.ts";

const id = Number(process.argv[2] ?? 1);
const free = Number(process.argv[3] ?? 1);
const data = JSON.parse(readFileSync("public/data/players.json", "utf8"));
const byId = new Map<number, any>(data.players.map((p: any) => [p.id, p]));

const team = await loadTeam(id);
const tenth = (x: number) => Math.round(x * 10);
const sell = sellingPrices(team.squad, team.transfers, (e) => tenth(byId.get(e).cost), (e) => tenth(byId.get(e).start));
const sumSell = [...sell.values()].reduce((a, b) => a + b, 0);
console.log(team.title, "GW", team.event, "| bank", team.bank / 10, "| API value", team.teamValue / 10, "| my sell sum", sumSell / 10);

const cands: Candidate[] = data.players.map((p: any) => ({
  id: p.id, name: p.name, pos: p.pos, team: p.team, buy: tenth(p.cost), gw: p.gw,
}));
const highs = await highsLoader();
const t0 = Date.now();
const res = await planTransfers(highs as any, cands, team.squad, sell, team.bank, free, 4);
console.log("solved in", Date.now() - t0, "ms");
const nm = (i: number) => byId.get(i).name;
for (const s of res) {
  console.log(`k=${s.k} ep=${s.ep.toFixed(1)} hit=${s.hit} net=${s.net.toFixed(1)} bank=${s.bank / 10}`,
    s.out.map(nm).join(",") + " -> " + s.in.map(nm).join(","));
}
