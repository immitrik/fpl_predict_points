import { useMemo, useState } from "react";
import type { Player, Pos } from "./types";
import { heat, fxLabel } from "./util";

type SortKey = "total" | "cost" | "own" | "value" | "pts" | number; // number = gw index

const POSITIONS: ("ALL" | Pos)[] = ["ALL", "GKP", "DEF", "MID", "FWD"];
const PAGE = 100;

interface Props {
  players: Player[];
  gws: number[];
  onSelect: (id: number) => void;
}

export default function PlayersTable({ players, gws, onSelect }: Props) {
  const [pos, setPos] = useState<"ALL" | Pos>("ALL");
  const [team, setTeam] = useState("ALL");
  const [query, setQuery] = useState("");
  const costCap = useMemo(() => Math.ceil(Math.max(...players.map((p) => p.cost)) * 2) / 2, [players]);
  const [maxCostPick, setMaxCost] = useState<number | null>(null);
  const maxCost = maxCostPick ?? costCap;
  const [hideOut, setHideOut] = useState(true);
  const [sort, setSort] = useState<SortKey>("total");
  const [desc, setDesc] = useState(true);
  const [limit, setLimit] = useState(PAGE);

  const teams = useMemo(() => [...new Set(players.map((p) => p.team))].sort(), [players]);

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    const val = (p: Player): number => {
      if (typeof sort === "number") return p.gw[sort];
      if (sort === "value") return p.total / p.cost;
      return p[sort];
    };
    return players
      .filter((p) => (pos === "ALL" || p.pos === pos) && (team === "ALL" || p.team === team))
      .filter((p) => p.cost <= maxCost && (!hideOut || p.fx.some((x) => x.av > 0)))
      .filter((p) => !q || p.name.toLowerCase().includes(q))
      .sort((a, b) => (desc ? val(b) - val(a) : val(a) - val(b)));
  }, [players, pos, team, query, maxCost, hideOut, sort, desc]);

  const setSortKey = (k: SortKey) => {
    if (k === sort) setDesc(!desc);
    else {
      setSort(k);
      setDesc(true);
    }
    setLimit(PAGE);
  };
  const arrow = (k: SortKey) => (sort === k ? (desc ? " ▾" : " ▴") : "");
  const reset = () => setLimit(PAGE);

  return (
    <section>
      <div className="filters">
        <div className="chips" role="group" aria-label="Position">
          {POSITIONS.map((p) => (
            <button
              key={p}
              className={pos === p ? "chip active" : "chip"}
              onClick={() => {
                setPos(p);
                reset();
              }}
            >
              {p === "ALL" ? "All" : p}
            </button>
          ))}
        </div>
        <input
          type="search"
          placeholder="Search player…"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            reset();
          }}
        />
        <select
          value={team}
          onChange={(e) => {
            setTeam(e.target.value);
            reset();
          }}
          aria-label="Team"
        >
          <option value="ALL">All teams</option>
          {teams.map((t) => (
            <option key={t}>{t}</option>
          ))}
        </select>
        <label className="range">
          Max price £{maxCost.toFixed(1)}m
          <input
            type="range"
            min={4}
            max={costCap}
            step={0.5}
            value={maxCost}
            onChange={(e) => {
              setMaxCost(Number(e.target.value));
              reset();
            }}
          />
        </label>
        <label className="check">
          <input type="checkbox" checked={hideOut} onChange={(e) => setHideOut(e.target.checked)} />
          Hide unavailable
        </label>
      </div>

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th className="left">Player</th>
              <th onClick={() => setSortKey("cost")} className="sortable">
                Price{arrow("cost")}
              </th>
              <th onClick={() => setSortKey("own")} className="sortable hide-sm">
                Own %{arrow("own")}
              </th>
              <th onClick={() => setSortKey("pts")} className="sortable hide-sm">
                Pts{arrow("pts")}
              </th>
              {gws.map((g, i) => (
                <th key={g} onClick={() => setSortKey(i)} className="sortable">
                  GW{g}
                  {arrow(i)}
                </th>
              ))}
              <th onClick={() => setSortKey("total")} className="sortable total">
                Total{arrow("total")}
              </th>
              <th onClick={() => setSortKey("value")} className="sortable hide-sm">
                Pts/£m{arrow("value")}
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.slice(0, limit).map((p) => (
              <tr key={p.id} onClick={() => onSelect(p.id)} tabIndex={0}
                  onKeyDown={(e) => e.key === "Enter" && onSelect(p.id)}>
                <td className="left">
                  <span className={`pos ${p.pos}`}>{p.pos}</span>
                  <span className="name">{p.name}</span>
                  <span className="team">{p.team}</span>
                  {p.roles.pen >= 1 && <span className="tag" title="First-choice penalty taker">P</span>}
                  {p.chance !== null && p.chance < 100 && (
                    <span className={p.chance <= 25 ? "flag red" : "flag amber"} title={p.news}>
                      {p.chance}%
                    </span>
                  )}
                </td>
                <td>£{p.cost.toFixed(1)}</td>
                <td className="hide-sm">{p.own.toFixed(1)}</td>
                <td className="hide-sm">{p.pts}</td>
                {p.gw.map((x, i) => (
                  <td key={i} className="heat" style={heat(x)}>
                    <b>{x.toFixed(1)}</b>
                    <small>{fxLabel(p, gws[i])}</small>
                  </td>
                ))}
                <td className="total">
                  <b>{p.total.toFixed(1)}</b>
                </td>
                <td className="hide-sm">{(p.total / p.cost).toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="muted count">
        {Math.min(limit, rows.length)} of {rows.length} players
        {limit < rows.length && (
          <button className="link" onClick={() => setLimit(limit + PAGE)}>
            Show more
          </button>
        )}
      </p>
    </section>
  );
}
