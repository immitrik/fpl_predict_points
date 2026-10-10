import { useState } from "react";
import type { Team } from "./types";
import { ease } from "./util";

type Mode = "overall" | "attack" | "defence";

interface Props {
  teams: Team[];
  gws: number[];
}

export default function FixtureTicker({ teams, gws }: Props) {
  const [mode, setMode] = useState<Mode>("overall");

  // Higher = easier. Attack: expected goals scored; defence: expected goals not conceded.
  const score = (gf: number, ga: number) =>
    mode === "attack" ? gf - 1.4 : mode === "defence" ? 1.4 - ga : gf - ga;

  const rows = teams
    .map((t) => ({
      t,
      total: t.fx.reduce((s, f) => s + score(f.gf, f.ga), 0),
    }))
    .sort((a, b) => b.total - a.total);

  return (
    <section>
      <div className="filters">
        <div className="chips" role="group" aria-label="Mode">
          {(["overall", "attack", "defence"] as Mode[]).map((m) => (
            <button key={m} className={mode === m ? "chip active" : "chip"} onClick={() => setMode(m)}>
              {m[0].toUpperCase() + m.slice(1)}
            </button>
          ))}
        </div>
        <span className="muted">
          Green = easier fixtures (from model-expected goals, incl. market odds). Sorted by ease.
        </span>
      </div>
      <div className="table-wrap">
        <table className="ticker">
          <thead>
            <tr>
              <th className="left">Team</th>
              {gws.map((g) => (
                <th key={g}>GW{g}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map(({ t }) => (
              <tr key={t.team}>
                <td className="left">
                  <b>{t.team}</b>
                </td>
                {gws.map((g) => {
                  const f = t.fx.filter((x) => x.r === g);
                  return (
                    <td key={g} className="cells">
                      {f.length === 0 && <span className="blank">–</span>}
                      {f.map((x, i) => (
                        <span key={i} className="fxcell" style={ease(score(x.gf, x.ga))}
                              title={`xG for ${x.gf.toFixed(2)} · against ${x.ga.toFixed(2)}`}>
                          {x.o} {x.h ? "H" : "A"}
                        </span>
                      ))}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
