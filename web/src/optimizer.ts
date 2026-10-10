// Transfer planner: picks the squad (and per-gameweek lineups) that maximises expected points
// over the horizon, for a fixed number of transfers, as an integer linear programme (HiGHS).
// Kept free of browser/Vite specifics so it can also run under node for testing.

export type Pos = "GKP" | "DEF" | "MID" | "FWD";

export interface Candidate {
  id: number;
  name: string;
  pos: Pos;
  team: string;
  buy: number; // current price in tenths of £m (what a transfer in costs)
  gw: number[]; // expected points per gameweek
}

export interface Lineup {
  gw: number; // index into the horizon
  xi: number[];
  captain: number;
}

export interface Scenario {
  k: number; // number of transfers
  hit: number; // points deducted for extra transfers
  ep: number; // expected points over the horizon, before the hit
  net: number; // ep - hit
  perGw: number[]; // expected points of the best XI (captain doubled) in each gameweek of the horizon
  out: number[];
  in: number[];
  squad: number[];
  bank: number; // tenths of £m left after the transfers
  lineups: Lineup[];
}

interface Highs {
  solve(problem: string, options?: Record<string, unknown>): {
    Status: string;
    Columns: Record<string, unknown>;
  };
}

export const SQUAD = { GKP: 2, DEF: 5, MID: 5, FWD: 3 } as const;
const XI_MIN = { GKP: 1, DEF: 3, MID: 2, FWD: 1 } as const;
const XI_MAX = { GKP: 1, DEF: 5, MID: 5, FWD: 3 } as const;
const POSITIONS: Pos[] = ["GKP", "DEF", "MID", "FWD"];
const HIT = 4;

/** Squad plus the best candidates per position (by total and by points-per-price). */
export function buildPool(all: Candidate[], squadIds: number[]): Candidate[] {
  const keep = new Set(squadIds);
  const total = (p: Candidate) => p.gw.reduce((a, b) => a + b, 0);
  for (const pos of POSITIONS) {
    const ps = all.filter((p) => p.pos === pos);
    ps.sort((a, b) => total(b) - total(a));
    ps.slice(0, 40).forEach((p) => keep.add(p.id));
    ps.filter((p) => p.buy > 0)
      .sort((a, b) => total(b) / b.buy - total(a) / a.buy)
      .slice(0, 15)
      .forEach((p) => keep.add(p.id));
  }
  return all.filter((p) => keep.has(p.id));
}

function terms(parts: string[]): string {
  // LP-format lines are best kept short: wrap every few terms
  const lines: string[] = [];
  for (let i = 0; i < parts.length; i += 8) lines.push("  " + parts.slice(i, i + 8).join(" "));
  return lines.join("\n");
}

function signed(coef: number, name: string): string {
  return `${coef >= 0 ? "+" : "-"} ${Math.abs(coef).toFixed(4)} ${name}`;
}

export function buildLp(
  pool: Candidate[],
  squadIds: number[],
  sell: Map<number, number>,
  bank: number,
  k: number,
  horizon: number,
): string {
  const old = new Set(squadIds);
  const obj: string[] = [];
  const cons: string[] = [];
  const bin: string[] = [];
  const x = (p: Candidate) => `x${p.id}`;
  const y = (p: Candidate, g: number) => `y${p.id}_${g}`;
  const c = (p: Candidate, g: number) => `c${p.id}_${g}`;

  for (const p of pool) bin.push(x(p));
  const sellOf = (p: Candidate) => sell.get(p.id) ?? p.buy;

  // squad composition, club limit, budget, number of transfers
  for (const pos of POSITIONS) {
    cons.push(` sq_${pos}: ${terms(pool.filter((p) => p.pos === pos).map((p) => `+ 1 ${x(p)}`))} = ${SQUAD[pos]}`);
  }
  const clubs = [...new Set(pool.map((p) => p.team))];
  clubs.forEach((t, i) =>
    cons.push(` club${i}: ${terms(pool.filter((p) => p.team === t).map((p) => `+ 1 ${x(p)}`))} <= 3`),
  );
  const refund = squadIds.reduce((s, id) => s + (sell.get(id) ?? 0), 0);
  cons.push(
    ` budget: ${terms(pool.map((p) => `+ ${old.has(p.id) ? sellOf(p) : p.buy} ${x(p)}`))} <= ${bank + refund}`,
  );
  const fresh = pool.filter((p) => !old.has(p.id));
  if (fresh.length) cons.push(` ntrans: ${terms(fresh.map((p) => `+ 1 ${x(p)}`))} = ${k}`);

  for (let g = 0; g < horizon; g++) {
    const top = [...pool].sort((a, b) => b.gw[g] - a.gw[g]).slice(0, 25); // captain candidates
    cons.push(` xi${g}: ${terms(pool.map((p) => `+ 1 ${y(p, g)}`))} = 11`);
    for (const pos of POSITIONS) {
      const ps = pool.filter((p) => p.pos === pos);
      const sum = terms(ps.map((p) => `+ 1 ${y(p, g)}`));
      cons.push(` xmin${pos}${g}: ${sum} >= ${XI_MIN[pos]}`);
      cons.push(` xmax${pos}${g}: ${sum} <= ${XI_MAX[pos]}`);
    }
    for (const p of pool) {
      cons.push(` own${p.id}_${g}: + 1 ${y(p, g)} - 1 ${x(p)} <= 0`);
      bin.push(y(p, g));
      obj.push(signed(p.gw[g], y(p, g)));
    }
    cons.push(` cap${g}: ${terms(top.map((p) => `+ 1 ${c(p, g)}`))} = 1`);
    for (const p of top) {
      cons.push(` capxi${p.id}_${g}: + 1 ${c(p, g)} - 1 ${y(p, g)} <= 0`);
      bin.push(c(p, g));
      obj.push(signed(p.gw[g], c(p, g)));
    }
  }

  return `Maximize\n obj:\n${terms(obj)}\nSubject To\n${cons.join("\n")}\nBinary\n${terms(bin.map((b) => b))}\nEnd\n`;
}

export function solveScenario(
  highs: Highs,
  pool: Candidate[],
  squadIds: number[],
  sell: Map<number, number>,
  bank: number,
  k: number,
  freeTransfers: number,
  horizon: number,
): Scenario | null {
  const lp = buildLp(pool, squadIds, sell, bank, k, horizon);
  const sol = highs.solve(lp, { mip_rel_gap: 0.0005, time_limit: 30 });
  if (sol.Status !== "Optimal" && sol.Status !== "Time limit reached") return null;
  const on = (name: string) => ((sol.Columns[name] as { Primal?: number } | undefined)?.Primal ?? 0) > 0.5;

  const old = new Set(squadIds);
  const squad = pool.filter((p) => on(`x${p.id}`)).map((p) => p.id);
  if (squad.length !== 15) return null;
  const lineups: Lineup[] = [];
  const perGw: number[] = [];
  let ep = 0;
  for (let g = 0; g < horizon; g++) {
    const xi = pool.filter((p) => on(`y${p.id}_${g}`));
    const cap = pool.find((p) => on(`c${p.id}_${g}`));
    const gwPts = xi.reduce((s, p) => s + p.gw[g], 0) + (cap ? cap.gw[g] : 0);
    perGw.push(gwPts);
    ep += gwPts;
    lineups.push({ gw: g, xi: xi.map((p) => p.id), captain: cap?.id ?? xi[0].id });
  }
  const priceOf = new Map(pool.map((p) => [p.id, p.buy]));
  const spent = squad.filter((id) => !old.has(id)).reduce((s, id) => s + (priceOf.get(id) ?? 0), 0);
  const refunded = squadIds.filter((id) => !squad.includes(id)).reduce((s, id) => s + (sell.get(id) ?? 0), 0);
  const hit = HIT * Math.max(0, k - freeTransfers);
  // transfers keep the position, so sorting both lists by position pairs each sale with its purchase
  const posOf = new Map(pool.map((p) => [p.id, POSITIONS.indexOf(p.pos)]));
  const byPos = (a: number, b: number) => (posOf.get(a) ?? 0) - (posOf.get(b) ?? 0) || a - b;
  return {
    k,
    hit,
    ep,
    net: ep - hit,
    perGw,
    out: squadIds.filter((id) => !squad.includes(id)).sort(byPos),
    in: squad.filter((id) => !old.has(id)).sort(byPos),
    squad,
    bank: bank + refunded - spent,
    lineups,
  };
}

/** Best scenario for each number of transfers 0..maxK (infeasible ones are skipped). */
export async function planTransfers(
  highs: Highs,
  all: Candidate[],
  squadIds: number[],
  sell: Map<number, number>,
  bank: number,
  freeTransfers: number,
  maxK: number,
  onProgress?: (k: number) => void,
): Promise<Scenario[]> {
  const pool = buildPool(all, squadIds);
  const horizon = pool[0]?.gw.length ?? 0;
  const out: Scenario[] = [];
  for (let k = 0; k <= maxK; k++) {
    onProgress?.(k);
    await new Promise((r) => setTimeout(r, 0)); // let the UI repaint between solves
    const s = solveScenario(highs, pool, squadIds, sell, bank, k, freeTransfers, horizon);
    if (s) out.push(s);
  }
  return out;
}
