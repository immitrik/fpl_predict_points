import { useEffect, useMemo, useState } from "react";
import type { Player, Pos } from "./types";
import { loadTeam, parsePasted, sellingPrices, PROXY_KEY, type LoadedTeam } from "./fplApi";
import { SQUAD, planTransfers, type Candidate, type Scenario } from "./optimizer";

const POS_ORDER: Pos[] = ["GKP", "DEF", "MID", "FWD"];
const tenth = (x: number) => Math.round(x * 10);
const money = (t: number) => `£${(t / 10).toFixed(1)}m`;

interface Props {
  players: Player[];
  gws: number[];
  nextEvent: number;
}

interface Squad {
  title: string;
  ids: number[];
  bank: number; // tenths
  sell: Map<number, number>;
}

async function loadHighs() {
  const [{ default: loader }, wasm] = await Promise.all([
    import("highs"),
    import("highs/runtime?url"),
  ]);
  return loader({ locateFile: () => wasm.default });
}

export default function Planner({ players, gws, nextEvent }: Props) {
  // transfers made now only affect gameweeks whose deadline is still ahead
  const from = Math.max(0, gws.findIndex((g) => g >= nextEvent));
  const hz = gws.slice(from);
  const params = new URLSearchParams(window.location.search);
  const [teamId, setTeamId] = useState(params.get("t") ?? "");
  const [free, setFree] = useState(1);
  const [autoFree, setAutoFree] = useState(false); // free transfers were read from the team's history
  const [win, setWin] = useState<[number, number]>([0, Math.max(0, hz.length - 1)]); // gameweeks to optimise for
  const [squad, setSquad] = useState<Squad | null>(null);
  const [manual, setManual] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [results, setResults] = useState<Scenario[] | null>(null);
  const [picked, setPicked] = useState<number | null>(null);

  const byId = useMemo(() => new Map(players.map((p) => [p.id, p])), [players]);
  const candidates: Candidate[] = useMemo(
    () =>
      players.map((p) => ({
        id: p.id,
        name: p.name,
        pos: p.pos,
        team: p.team,
        buy: tenth(p.cost),
        gw: p.gw.slice(from + win[0], from + win[1] + 1),
      })),
    [players, from, win],
  );
  const wgws = hz.slice(win[0], win[1] + 1); // gameweek numbers in the chosen window
  const changeWin = (w: [number, number]) => {
    setWin(w);
    setResults(null);
  };

  const applyTeam = (t: LoadedTeam) => {
    const missing = t.squad.filter((e) => !byId.has(e));
    if (missing.length) throw new Error("Some squad players are not in the prediction data (removed from the game?).");
    const sell = sellingPrices(
      t.squad,
      t.transfers,
      (e) => tenth(byId.get(e)!.cost),
      (e) => tenth(byId.get(e)!.start),
    );
    setSquad({ title: t.title, ids: t.squad, bank: t.bank, sell });
    setManual(false);
    setResults(null);
    if (t.freeTransfers !== null) {
      setFree(t.freeTransfers);
      setAutoFree(true);
    } else {
      setAutoFree(false);
    }
  };

  const fromPaste = (picks: string, transfers: string) => {
    try {
      setError(null);
      applyTeam(parsePasted(picks, transfers));
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const fromApi = async () => {
    setError(null);
    setResults(null);
    const id = Number(teamId.trim());
    if (!Number.isInteger(id) || id <= 0) return setError("Enter a numeric team ID (see the number in your FPL team URL).");
    setBusy("Loading team…");
    try {
      applyTeam(await loadTeam(id));
    } catch (e) {
      setError(`${(e as Error).message}. You can enter the squad manually below.`);
      setSquad(null);
    } finally {
      setBusy(null);
    }
  };

  const run = async () => {
    if (!squad) return;
    const counts: Record<string, number> = { GKP: 0, DEF: 0, MID: 0, FWD: 0 };
    squad.ids.forEach((e) => counts[byId.get(e)!.pos]++);
    if (squad.ids.length !== 15 || POS_ORDER.some((p) => counts[p] !== SQUAD[p])) {
      return setError("The squad must have 15 players: 2 GKP, 5 DEF, 5 MID, 3 FWD.");
    }
    setError(null);
    setResults(null);
    try {
      setBusy("Loading optimiser…");
      const highs = await loadHighs();
      const res = await planTransfers(highs, candidates, squad.ids, squad.sell, squad.bank, free, 4, (k) =>
        setBusy(`Optimising for ${k} transfer${k === 1 ? "" : "s"}…`),
      );
      setResults(res);
      const best = res.reduce((a, b) => (b.net > a.net ? b : a));
      setPicked(best.k);
    } catch (e) {
      setError(`Optimiser failed: ${(e as Error).message}`);
    } finally {
      setBusy(null);
    }
  };

  // ?t=<id>&run=1 opens the planner pre-filled (handy for sharing)
  useEffect(() => {
    if (params.get("t")) void fromApi();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => {
    if (squad && params.get("run") === "1" && !results && !busy) void run();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [squad]);

  const nameOf = (id: number) => byId.get(id)?.name ?? String(id);
  const base = results?.find((r) => r.k === 0);
  const best = results?.reduce((a, b) => (b.net > a.net ? b : a));
  const shown = results?.find((r) => r.k === picked) ?? null;

  return (
    <section className="planner">
      <h2>Transfer planner</h2>
      <p className="muted">
        Enter your FPL team ID and get the best squad with 1–4 transfers for the gameweeks you pick (one week
        or several), counting a −4 point hit for every transfer beyond your free ones.
      </p>

      <div className="filters">
        <label className="field">
          Team ID
          <input
            inputMode="numeric"
            placeholder="e.g. 123456"
            value={teamId}
            onChange={(e) => setTeamId(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && void fromApi()}
          />
        </label>
        <label className="field">
          Free transfers
          <select
            value={free}
            onChange={(e) => {
              setFree(Number(e.target.value));
              setAutoFree(false);
              setResults(null);
            }}
          >
            {[0, 1, 2, 3, 4, 5].map((n) => (
              <option key={n}>{n}</option>
            ))}
          </select>
          {autoFree && <small className="auto">auto-detected</small>}
        </label>
        <button className="primary" onClick={() => void fromApi()} disabled={!!busy}>
          Load team
        </button>
        <button className="chip" onClick={() => { setManual(!manual); setSquad(squad ?? { title: "Manual squad", ids: [], bank: 0, sell: new Map() }); }}>
          Enter squad manually
        </button>
      </div>
      <p className="muted small">
        Your team ID is the number in the URL of your FPL points page (…/entry/<b>123456</b>/event/…). The FPL
        API blocks direct browser access, so loading by ID needs a CORS proxy (configured by the site owner, or
        your own); without one, paste the data below or enter the squad manually. <ProxySetting />
      </p>

      {error && <p className="error">{error}</p>}
      {busy && <p className="muted">{busy}</p>}

      <PasteTeam teamId={teamId} onLoad={fromPaste} />

      {manual && squad && (
        <ManualSquad players={players} squad={squad} setSquad={(s) => { setSquad(s); setResults(null); }} />
      )}

      {squad && squad.ids.length > 0 && (
        <>
          <h3>
            {squad.title} · bank {money(squad.bank)}
          </h3>
          <SquadTable ids={squad.ids} byId={byId} sell={squad.sell} from={from + win[0]} to={from + win[1] + 1} labels={wgws} />
          <div className="filters winpick">
            <span className="muted">Optimise for</span>
            <label className="field">
              From
              <select value={win[0]} onChange={(e) => changeWin([Number(e.target.value), Math.max(win[1], Number(e.target.value))])}>
                {hz.map((g, i) => (
                  <option key={g} value={i}>
                    GW{g}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              To
              <select value={win[1]} onChange={(e) => changeWin([Math.min(win[0], Number(e.target.value)), Number(e.target.value)])}>
                {hz.map((g, i) => (
                  <option key={g} value={i} disabled={i < win[0]}>
                    GW{g}
                  </option>
                ))}
              </select>
            </label>
            <div className="chips">
              {hz.map((g, i) => (
                <button key={g} className={win[0] === i && win[1] === i ? "chip active" : "chip"} onClick={() => changeWin([i, i])}>
                  GW{g} only
                </button>
              ))}
              <button className={win[0] === 0 && win[1] === hz.length - 1 ? "chip active" : "chip"} onClick={() => changeWin([0, hz.length - 1])}>
                All
              </button>
            </div>
          </div>
          <p>
            <button className="primary" onClick={() => void run()} disabled={!!busy || squad.ids.length !== 15}>
              Build best team
            </button>
          </p>
        </>
      )}

      {results && base && best && (
        <>
          <h3>Options</h3>
          <div className="table-wrap">
            <table className="detail plan">
              <thead>
                <tr>
                  <th className="left">Transfers</th>
                  <th>Exp. pts</th>
                  <th>Hit</th>
                  <th>Net</th>
                  <th>vs current</th>
                  <th className="left">Out → In</th>
                  <th>Bank</th>
                </tr>
              </thead>
              <tbody>
                {results.map((r) => (
                  <tr key={r.k} className={r.k === picked ? "sel" : ""} onClick={() => setPicked(r.k)}>
                    <td className="left">
                      {r.k}
                      {r === best && <span className="tag">best</span>}
                    </td>
                    <td>{r.ep.toFixed(1)}</td>
                    <td>{r.hit ? `−${r.hit}` : "0"}</td>
                    <td>
                      <b>{r.net.toFixed(1)}</b>
                    </td>
                    <td className={r.net - base.net > 0.05 ? "pos-gain" : r.net - base.net < -0.05 ? "neg-gain" : ""}>
                      {r.k === 0 ? "–" : `${r.net - base.net >= 0 ? "+" : ""}${(r.net - base.net).toFixed(1)}`}
                    </td>
                    <td className="left wrap">
                      {r.k === 0
                        ? "keep squad"
                        : r.out.map((o, i) => (
                            <span key={o} className="swap">
                              {nameOf(o)} → {nameOf(r.in[i] ?? 0)}
                            </span>
                          ))}
                    </td>
                    <td>{money(r.bank)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="muted small">
            Expected points are for {wgws.length === 1 ? `GW${wgws[0]}` : `GW${wgws[0]}–${wgws[wgws.length - 1]}`}{" "}
            (gameweeks already under way cannot be changed), with the best XI chosen in each gameweek and the
            captain counted twice. Out→In pairs are listed by position. Transfers are made now and kept for the
            whole window; chips and later transfers are not modelled.
          </p>
          {shown && (
            <>
              <WeekTable base={base} scenario={shown} gws={wgws} />
              <LineupView scenario={shown} byId={byId} gws={wgws} from={from + win[0]} />
            </>
          )}
        </>
      )}
    </section>
  );
}

function PasteTeam({ teamId, onLoad }: { teamId: string; onLoad: (picks: string, transfers: string) => void }) {
  const [picks, setPicks] = useState("");
  const [transfers, setTransfers] = useState("");
  const id = teamId.trim() || "YOUR_ID";
  return (
    <details className="paste">
      <summary>No proxy? Paste your team data instead</summary>
      <ol className="small muted">
        <li>
          Open <code>fantasy.premierleague.com/api/entry/{id}/event/GW/picks/</code> (GW = the current gameweek
          number), select all, copy, and paste it into the first box.
        </li>
        <li>
          Optional, for exact selling prices: do the same with{" "}
          <code>fantasy.premierleague.com/api/entry/{id}/transfers/</code> and paste into the second box.
        </li>
      </ol>
      <textarea
        placeholder='Picks JSON, starts with {"active_chip": …'
        value={picks}
        onChange={(e) => setPicks(e.target.value)}
      />
      <textarea
        placeholder="Transfers JSON (optional), starts with [{ …"
        value={transfers}
        onChange={(e) => setTransfers(e.target.value)}
      />
      <p>
        <button className="chip" onClick={() => onLoad(picks, transfers)} disabled={!picks.trim()}>
          Use pasted data
        </button>
      </p>
    </details>
  );
}

function ProxySetting() {
  const [open, setOpen] = useState(false);
  const [val, setVal] = useState(() => {
    try {
      return localStorage.getItem(PROXY_KEY) ?? "";
    } catch {
      return "";
    }
  });
  if (!open) return <button className="link" onClick={() => setOpen(true)}>Use my own proxy</button>;
  return (
    <span className="proxy">
      <input
        placeholder="https://my-proxy.example/?u={url}"
        value={val}
        onChange={(e) => {
          setVal(e.target.value);
          try {
            if (e.target.value) localStorage.setItem(PROXY_KEY, e.target.value);
            else localStorage.removeItem(PROXY_KEY);
          } catch {
            /* ignore */
          }
        }}
      />
    </span>
  );
}

function WeekTable({ base, scenario, gws }: { base: Scenario; scenario: Scenario; gws: number[] }) {
  const diff = (g: number) => scenario.perGw[g] - base.perGw[g];
  const fmt = (x: number) => `${x >= 0 ? "+" : ""}${x.toFixed(1)}`;
  return (
    <>
      <h3>By gameweek</h3>
      <div className="table-wrap">
        <table className="detail">
          <thead>
            <tr>
              <th className="left">Squad</th>
              {gws.map((g) => (
                <th key={g}>GW{g}</th>
              ))}
              <th>Total</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td className="left">Current (no transfers)</td>
              {base.perGw.map((x, i) => (
                <td key={i}>{x.toFixed(1)}</td>
              ))}
              <td>
                <b>{base.ep.toFixed(1)}</b>
              </td>
            </tr>
            <tr>
              <td className="left">
                With {scenario.k} transfer{scenario.k === 1 ? "" : "s"}
              </td>
              {scenario.perGw.map((x, i) => (
                <td key={i}>{x.toFixed(1)}</td>
              ))}
              <td>
                <b>{scenario.ep.toFixed(1)}</b>
              </td>
            </tr>
            <tr>
              <td className="left muted">Difference</td>
              {scenario.perGw.map((_, i) => (
                <td key={i} className={diff(i) > 0.05 ? "pos-gain" : diff(i) < -0.05 ? "neg-gain" : ""}>
                  {fmt(diff(i))}
                </td>
              ))}
              <td className={scenario.ep - base.ep > 0.05 ? "pos-gain" : ""}>{fmt(scenario.ep - base.ep)}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </>
  );
}

function SquadTable({ ids, byId, sell, from, to, labels }: { ids: number[]; byId: Map<number, Player>; sell: Map<number, number>; from: number; to: number; labels: number[] }) {
  const rows = [...ids]
    .map((id) => byId.get(id)!)
    .sort((a, b) => POS_ORDER.indexOf(a.pos) - POS_ORDER.indexOf(b.pos) || b.total - a.total);
  return (
    <div className="table-wrap">
      <table className="detail">
        <thead>
          <tr>
            <th className="left">Player</th>
            <th>Sell</th>
            <th>Now</th>
            {rows[0] && rows[0].gw.slice(from, to).map((_, i) => <th key={i}>GW{labels[i]}</th>)}
            <th>Total</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((p) => (
            <tr key={p.id}>
              <td className="left">
                <span className={`pos ${p.pos}`}>{p.pos}</span>
                {p.name} <span className="team">{p.team}</span>
              </td>
              <td>{sell.has(p.id) ? money(sell.get(p.id)!) : "–"}</td>
              <td>£{p.cost.toFixed(1)}m</td>
              {p.gw.slice(from, to).map((x, i) => (
                <td key={i}>{x.toFixed(1)}</td>
              ))}
              <td>
                <b>{p.gw.slice(from, to).reduce((a, b) => a + b, 0).toFixed(1)}</b>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function LineupView({ scenario, byId, gws, from }: { scenario: Scenario; byId: Map<number, Player>; gws: number[]; from: number }) {
  const [g, setG] = useState(0);
  const lu = scenario.lineups[g];
  const xi = lu.xi.map((id) => byId.get(id)!);
  const bench = scenario.squad.filter((id) => !lu.xi.includes(id)).map((id) => byId.get(id)!);
  return (
    <div className="lineup">
      <h3>Lineup for {scenario.k} transfer{scenario.k === 1 ? "" : "s"}</h3>
      <div className="chips">
        {gws.map((gw, i) => (
          <button key={gw} className={g === i ? "chip active" : "chip"} onClick={() => setG(i)}>
            GW{gw}
          </button>
        ))}
      </div>
      <div className="pitch">
        {POS_ORDER.map((pos) => (
          <div key={pos} className="row">
            {xi
              .filter((p) => p.pos === pos)
              .map((p) => (
                <div key={p.id} className={p.id === lu.captain ? "card cap" : "card"}>
                  <b>{p.name}</b>
                  <small>
                    {p.team} · {p.gw[g + from].toFixed(1)}
                    {p.id === lu.captain && " · C"}
                  </small>
                </div>
              ))}
          </div>
        ))}
      </div>
      <p className="muted small">
        Bench: {bench.map((p) => `${p.name} (${p.gw[g + from].toFixed(1)})`).join(", ")}
      </p>
    </div>
  );
}

function ManualSquad({ players, squad, setSquad }: { players: Player[]; squad: Squad; setSquad: (s: Squad) => void }) {
  const [q, setQ] = useState("");
  const byId = useMemo(() => new Map(players.map((p) => [p.id, p])), [players]);
  const matches = useMemo(() => {
    const s = q.trim().toLowerCase();
    if (!s) return [];
    return players
      .filter((p) => p.name.toLowerCase().includes(s) && !squad.ids.includes(p.id))
      .sort((a, b) => b.own - a.own)
      .slice(0, 8);
  }, [q, players, squad.ids]);

  const set = (ids: number[], bank = squad.bank) =>
    setSquad({
      ...squad,
      ids,
      bank,
      sell: new Map(ids.map((id) => [id, tenth(byId.get(id)!.cost)])), // manual entry: assume current price
    });

  return (
    <div className="manual">
      <h3>Manual squad ({squad.ids.length}/15)</h3>
      <div className="filters">
        <input type="search" placeholder="Add player…" value={q} onChange={(e) => setQ(e.target.value)} />
        <label className="field">
          Bank £m
          <input
            inputMode="decimal"
            value={(squad.bank / 10).toString()}
            onChange={(e) => set(squad.ids, tenth(Number(e.target.value) || 0))}
          />
        </label>
      </div>
      {matches.length > 0 && (
        <div className="chips wrapchips">
          {matches.map((p) => (
            <button key={p.id} className="chip" disabled={squad.ids.length >= 15} onClick={() => { set([...squad.ids, p.id]); setQ(""); }}>
              + {p.name} ({p.pos}, {p.team})
            </button>
          ))}
        </div>
      )}
      <div className="chips wrapchips">
        {squad.ids.map((id) => (
          <button key={id} className="chip active" onClick={() => set(squad.ids.filter((x) => x !== id))}>
            {byId.get(id)?.name} ×
          </button>
        ))}
      </div>
      <p className="muted small">Selling prices are assumed equal to current prices in manual mode.</p>
    </div>
  );
}
