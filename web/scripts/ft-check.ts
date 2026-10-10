// Dev check of the free-transfer simulation against hits actually charged, over many real teams.
// Usage: node scripts/ft-check.ts [fromId] [toId]
import { estimateFreeTransfers, type History } from "../src/fplApi.ts";

const from = Number(process.argv[2] ?? 1);
const to = Number(process.argv[3] ?? 200);
let teams = 0, checked = 0, mismatches = 0, withChips = 0;
const hist = async (id: number): Promise<History | null> => {
  try {
    const r = await fetch(`https://fantasy.premierleague.com/api/entry/${id}/history/`, { headers: { "User-Agent": "Mozilla/5.0" } });
    return r.ok ? ((await r.json()) as History) : null;
  } catch { return null; }
};
for (let id = from; id <= to; id += 8) {
  const batch = await Promise.all(Array.from({ length: 8 }, (_, i) => hist(id + i)));
  for (const h of batch) {
    if (!h) continue;
    teams++;
    const e = estimateFreeTransfers(h);
    checked += e.checked; mismatches += e.mismatches;
    if (e.mismatches) console.log("mismatch", JSON.stringify(h.current.map((c) => [c.event, c.event_transfers, c.event_transfers_cost])), JSON.stringify(h.chips.map((c) => [c.name, c.event])));
    if (h.chips.some((c) => c.name === "wildcard" || c.name === "freehit")) withChips++;
  }
}
console.log({ teams, withFreeChips: withChips, hitsChecked: checked, mismatches });
