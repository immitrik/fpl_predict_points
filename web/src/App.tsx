import { useEffect, useState } from "react";
import type { PlayersFile, TeamsFile } from "./types";
import PlayersTable from "./PlayersTable";
import PlayerModal from "./PlayerModal";
import FixtureTicker from "./FixtureTicker";

type Tab = "players" | "fixtures" | "about";
const TABS: { id: Tab; label: string }[] = [
  { id: "players", label: "Players" },
  { id: "fixtures", label: "Fixtures" },
  { id: "about", label: "About" },
];

async function load<T>(name: string): Promise<T> {
  const res = await fetch(`${import.meta.env.BASE_URL}data/${name}`);
  if (!res.ok) throw new Error(`${name}: ${res.status}`);
  return res.json();
}

function tabFromHash(): Tab {
  const h = window.location.hash.replace("#", "");
  return TABS.some((t) => t.id === h) ? (h as Tab) : "players";
}

export default function App() {
  const [players, setPlayers] = useState<PlayersFile | null>(null);
  const [teams, setTeams] = useState<TeamsFile | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>(tabFromHash);
  const [selected, setSelected] = useState<number | null>(() => {
    const id = Number(new URLSearchParams(window.location.search).get("p"));
    return id > 0 ? id : null;
  });

  // keep ?p=<id> in the URL so a player can be shared
  useEffect(() => {
    const url = new URL(window.location.href);
    if (selected) url.searchParams.set("p", String(selected));
    else url.searchParams.delete("p");
    window.history.replaceState(null, "", url);
  }, [selected]);

  useEffect(() => {
    Promise.all([load<PlayersFile>("players.json"), load<TeamsFile>("teams.json")])
      .then(([p, t]) => {
        setPlayers(p);
        setTeams(t);
      })
      .catch((e: Error) => setError(e.message));
    const onHash = () => setTab(tabFromHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const player = players?.players.find((p) => p.id === selected) ?? null;

  return (
    <div className="app">
      <header className="top">
        <div>
          <h1>FPL Predicted Points</h1>
          {players && (
            <p className="sub">
              Gameweeks {players.gws[0]}–{players.gws[players.gws.length - 1]} · {players.season} ·
              updated {new Date(players.generated_at).toLocaleString()}
            </p>
          )}
        </div>
        <nav className="tabs">
          {TABS.map((t) => (
            <a key={t.id} href={`#${t.id}`} className={tab === t.id ? "active" : ""}>
              {t.label}
            </a>
          ))}
        </nav>
      </header>

      {error && <p className="error">Could not load data: {error}</p>}
      {!players && !error && <p className="muted">Loading…</p>}

      {players && teams && (
        <main>
          {tab === "players" && (
            <PlayersTable players={players.players} gws={players.gws} onSelect={setSelected} />
          )}
          {tab === "fixtures" && <FixtureTicker teams={teams.teams} gws={teams.gws} />}
          {tab === "about" && <About model={players.model} />}
        </main>
      )}

      {player && players && (
        <PlayerModal player={player} gws={players.gws} onClose={() => setSelected(null)} />
      )}
    </div>
  );
}

function About({ model }: { model: string }) {
  return (
    <section className="about">
      <h2>How it works</h2>
      <p>
        For every player and every upcoming match we predict the individual scoring <em>events</em> —
        minutes, goals, assists, clean sheet, bonus, defensive contributions, saves, cards — and convert
        them to points with the official Fantasy Premier League scoring rules. Double gameweeks are
        summed, blank gameweeks give zero.
      </p>
      <ul>
        <li>
          <strong>Model:</strong> {model} ensemble trained on four seasons of player-match data.
          Predictions for later gameweeks are deliberately less certain than for the next one.
        </li>
        <li>
          <strong>Inputs:</strong> recent form (exponentially weighted), team attack and defence
          strength, home/away, rest days, price and ownership, plus betting-market implied goals where
          odds are already published.
        </li>
        <li>
          <strong>Availability:</strong> uses the official fitness flags. Injured and doubtful players
          are scaled down; long-term injury length is not modelled yet.
        </li>
        <li>
          <strong>Data:</strong> official FPL API, the vaastav/Fantasy-Premier-League archive and
          football-data.co.uk.
        </li>
      </ul>
      <p className="muted">
        Expected points are averages, not guarantees: single-match FPL scores are mostly noise, so use
        them to compare players rather than to predict exact scores.
      </p>
    </section>
  );
}
