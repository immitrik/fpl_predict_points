import { useEffect } from "react";
import type { FormMatch, Player } from "./types";
import { heat } from "./util";

interface Props {
  player: Player;
  gws: number[];
  onClose: () => void;
}

function FormChart({ form }: { form: FormMatch[] }) {
  if (!form.length) return <p className="muted">No matches played yet this season.</p>;
  const W = 48;
  const H = 100;
  const max = Math.max(8, ...form.map((m) => m.p));
  return (
    <svg
      role="img"
      aria-label="Points in recent matches"
      width={form.length * W}
      height={H + 50}
      viewBox={`0 0 ${form.length * W} ${H + 50}`}
      className="formchart"
    >
      {form.map((m, i) => {
        const h = Math.max(2, (Math.max(0, m.p) / max) * H);
        return (
          <g key={i} transform={`translate(${i * W},0)`}>
            <rect x={5} y={H - h + 14} width={W - 10} height={h} rx={3}
                  className={m.m === 0 ? "bar zero" : "bar"} />
            <text x={W / 2} y={H - h + 10} textAnchor="middle" className="barval">
              {m.p}
            </text>
            <text x={W / 2} y={H + 30} textAnchor="middle" className="barlab">
              {m.o}
            </text>
            <text x={W / 2} y={H + 43} textAnchor="middle" className="barlab sm">
              {m.h ? "H" : "A"} · {m.m}′
            </text>
          </g>
        );
      })}
    </svg>
  );
}

export default function PlayerModal({ player: p, gws, onClose }: Props) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const showSaves = p.pos === "GKP";
  const showAvail = p.fx.some((x) => x.av < 0.995);
  const roles = [
    ["Penalties", p.roles.pen],
    ["Corners", p.roles.cor],
    ["Free kicks", p.roles.fk],
  ].filter(([, v]) => (v as number) > 0) as [string, number][];
  const showDef = p.pos !== "FWD";

  return (
    <div className="overlay" onClick={onClose}>
      <div className="modal" role="dialog" aria-modal="true" aria-label={p.name}
           onClick={(e) => e.stopPropagation()}>
        <button className="close" onClick={onClose} aria-label="Close">×</button>
        <h2>
          <span className={`pos ${p.pos}`}>{p.pos}</span> {p.name} <span className="team">{p.team}</span>
        </h2>
        <p className="sub">
          £{p.cost.toFixed(1)}m · {p.own.toFixed(1)}% owned · {p.pts} pts in {p.mins} min this season
        </p>
        {p.news && (
          <p className={p.chance !== null && p.chance <= 25 ? "news red" : "news amber"}>
            {p.news}
          </p>
        )}
        {roles.length > 0 && (
          <p className="roles">
            {roles.map(([label, v]) => (
              <span key={label} className="role">
                {label}: {v >= 1 ? "1st" : v >= 0.5 ? "2nd" : "backup"}
              </span>
            ))}
          </p>
        )}

        <div className="summary">
          {gws.map((g, i) => (
            <div key={g} style={heat(p.gw[i])}>
              <small>GW{g}</small>
              <b>{p.gw[i].toFixed(1)}</b>
            </div>
          ))}
          <div className="sumtotal">
            <small>Total</small>
            <b>{p.total.toFixed(1)}</b>
          </div>
        </div>

        <h3>Recent form</h3>
        <FormChart form={p.form} />

        <h3>Upcoming matches</h3>
        <div className="table-wrap">
          <table className="detail">
            <thead>
              <tr>
                <th className="left">GW</th>
                <th className="left">Opponent</th>
                {showAvail && <th>Avail %</th>}
                <th>Min</th>
                <th>Goals</th>
                <th>Assists</th>
                {showDef && <th>CS %</th>}
                {showSaves && <th>Saves</th>}
                <th>Bonus</th>
                {p.pos !== "GKP" && <th>DC %</th>}
                <th>xPts</th>
              </tr>
            </thead>
            <tbody>
              {p.fx.map((x, i) => (
                <tr key={i}>
                  <td className="left">{x.r}</td>
                  <td className="left">{x.o} ({x.h ? "H" : "A"})</td>
                  {showAvail && <td>{(x.av * 100).toFixed(0)}</td>}
                  <td>{x.mn.toFixed(0)}</td>
                  <td>{x.g.toFixed(2)}</td>
                  <td>{x.a.toFixed(2)}</td>
                  {showDef && <td>{(x.cs * 100).toFixed(0)}</td>}
                  {showSaves && <td>{x.sv.toFixed(1)}</td>}
                  <td>{x.b.toFixed(2)}</td>
                  {p.pos !== "GKP" && <td>{(x.dc * 100).toFixed(0)}</td>}
                  <td className="heat" style={heat(x.xp)}><b>{x.xp.toFixed(1)}</b></td>
                </tr>
              ))}
              {!p.fx.length && (
                <tr><td colSpan={9} className="muted">No fixtures in this window.</td></tr>
              )}
            </tbody>
          </table>
        </div>
        <p className="muted small">
          Expected values per match. Goals, assists and bonus are expected counts; CS and DC are
          probabilities; all are scaled by the chance of playing. Availability comes from the injury
          news (return dates are parsed; unknown return dates use a conservative prior).
        </p>
      </div>
    </div>
  );
}
