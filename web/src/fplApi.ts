// Loading a manager's squad from the official FPL API.
// The API sends no CORS headers, so a browser on another origin cannot call it directly. Options:
//   1. a CORS proxy: the site owner's (VITE_FPL_PROXY, e.g. the Cloudflare Worker in /worker),
//      the visitor's own (saved in localStorage) or, best effort only, public ones;
//   2. pasting the JSON copied from the FPL site (parsePasted);
//   3. entering the squad manually in the UI.

const FPL = "https://fantasy.premierleague.com/api";

export const PROXY_KEY = "fpl_proxy"; // optional custom proxy template, "{url}" is replaced

// Public proxies are rate-limited and frequently down: last resort only.
const PUBLIC_PROXIES: ((u: string) => string)[] = [
  (u) => `https://api.allorigins.win/raw?url=${encodeURIComponent(u)}`,
];

function proxies(): ((u: string) => string)[] {
  const templates: string[] = [];
  const add = (t: string | null | undefined) => {
    if (t) templates.push(t);
  };
  add(new URLSearchParams(window.location.search).get("proxy")); // one-off, not persisted
  try {
    add(localStorage.getItem(PROXY_KEY));
  } catch {
    /* storage may be unavailable */
  }
  add(import.meta.env.VITE_FPL_PROXY); // set by the site owner at build time
  return [
    ...templates.map((t) => (u: string) => t.replace("{url}", encodeURIComponent(u))),
    ...PUBLIC_PROXIES,
  ];
}

async function getJson<T>(path: string): Promise<T> {
  const url = `${FPL}/${path}`;
  let lastError: unknown;
  for (const wrap of [(u: string) => u, ...proxies()]) {
    try {
      const res = await fetch(wrap(url));
      if (res.status === 404) throw new Error("Team not found");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return (await res.json()) as T;
    } catch (e) {
      if (e instanceof Error && e.message === "Team not found") throw e;
      lastError = e;
    }
  }
  throw new Error(`Could not reach the FPL API (${(lastError as Error)?.message ?? "network error"})`);
}

interface Entry {
  name: string;
  player_first_name: string;
  player_last_name: string;
  current_event: number;
}
export interface Picks {
  picks: { element: number }[];
  entry_history: { bank: number; value: number; event: number };
}
export interface Transfer {
  element_in: number;
  element_in_cost: number;
  element_out: number;
  element_out_cost: number;
  event: number;
  time: string;
}

export interface LoadedTeam {
  title: string;
  event: number;
  squad: number[]; // element ids
  bank: number; // tenths of £m
  teamValue: number; // tenths of £m, from the API (market value at current prices)
  transfers: Transfer[];
}

/** Squad as it stands now: the last deadline's picks with any transfers made since applied. */
export function buildTeam(title: string, event: number, picks: Picks, transfers: Transfer[]): LoadedTeam {
  let squad = picks.picks.map((p) => p.element);
  let bank = picks.entry_history.bank;
  const pending = transfers.filter((t) => t.event > event).sort((a, b) => a.time.localeCompare(b.time));
  for (const t of pending) {
    squad = squad.map((e) => (e === t.element_out ? t.element_in : e));
    bank += t.element_out_cost - t.element_in_cost;
  }
  return { title, event, squad, bank, teamValue: picks.entry_history.value, transfers };
}

export async function loadTeam(id: number): Promise<LoadedTeam> {
  const entry = await getJson<Entry>(`entry/${id}/`);
  let event = entry.current_event;
  let picks: Picks;
  try {
    picks = await getJson<Picks>(`entry/${id}/event/${event}/picks/`);
  } catch {
    event -= 1;
    picks = await getJson<Picks>(`entry/${id}/event/${event}/picks/`);
  }
  const transfers = await getJson<Transfer[]>(`entry/${id}/transfers/`);
  return buildTeam(`${entry.name} (${entry.player_first_name} ${entry.player_last_name})`, event, picks, transfers);
}

/** Build a team from JSON the user copied from the FPL site (no proxy needed). */
export function parsePasted(picksText: string, transfersText: string): LoadedTeam {
  let picks: Picks;
  try {
    picks = JSON.parse(picksText) as Picks;
  } catch {
    throw new Error("The picks text is not valid JSON");
  }
  if (!Array.isArray(picks.picks) || !picks.entry_history) {
    throw new Error("That does not look like an FPL picks response");
  }
  let transfers: Transfer[] = [];
  if (transfersText.trim()) {
    try {
      transfers = JSON.parse(transfersText) as Transfer[];
    } catch {
      throw new Error("The transfers text is not valid JSON");
    }
  }
  return buildTeam("Pasted team", picks.entry_history.event, picks, transfers);
}

/**
 * Selling prices (tenths of £m). FPL pays out only half of any price rise, rounded down:
 * sell = purchase + floor((now - purchase) / 2). The purchase price is the latest transfer-in
 * for the player, or his start-of-season price if he was in the original squad.
 */
export function sellingPrices(
  squad: number[],
  transfers: Transfer[],
  now: (id: number) => number,
  start: (id: number) => number,
): Map<number, number> {
  const out = new Map<number, number>();
  for (const id of squad) {
    const bought = transfers
      .filter((t) => t.element_in === id)
      .sort((a, b) => b.time.localeCompare(a.time))[0];
    const purchase = bought ? bought.element_in_cost : start(id);
    const n = now(id);
    out.set(id, n > purchase ? purchase + Math.floor((n - purchase) / 2) : n);
  }
  return out;
}
