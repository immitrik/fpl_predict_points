import type { CSSProperties } from "react";
import type { Player } from "./types";

/** Background shade for an expected-points cell (0 = none, ~8+ = strongest). */
export function heat(x: number): CSSProperties {
  const pct = Math.max(0, Math.min(1, x / 8)) * 75;
  return { background: `color-mix(in srgb, var(--good) ${pct}%, transparent)` };
}

/** "LIV (H)" labels for a gameweek; "DGW" players show both opponents, blanks show a dash. */
export function fxLabel(p: Player, gw: number): string {
  const f = p.fx.filter((x) => x.r === gw);
  if (!f.length) return "–";
  return f.map((x) => `${x.o} ${x.h ? "H" : "A"}`).join(", ");
}

/** Shade for fixture difficulty from expected goal difference (positive = easy). */
export function ease(gd: number): CSSProperties {
  const pct = Math.min(1, Math.abs(gd) / 1.5) * 70;
  const col = gd >= 0 ? "var(--good)" : "var(--bad)";
  return { background: `color-mix(in srgb, ${col} ${pct}%, transparent)` };
}
