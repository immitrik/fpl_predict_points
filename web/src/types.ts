export type Pos = "GKP" | "DEF" | "MID" | "FWD";

export interface Fixture {
  r: number; // gameweek
  o: string; // opponent (short name)
  h: boolean; // home
  xp: number; // expected points
  mn: number; // expected minutes
  av: number; // chance of being available (injury / suspension news)
  g: number; // expected goals
  a: number; // expected assists
  cs: number; // clean sheet probability (for the player)
  b: number; // expected bonus
  dc: number; // defensive contribution bonus probability
  sv: number; // expected saves
}

export interface FormMatch {
  r: number;
  o: string;
  h: boolean;
  p: number; // points
  m: number; // minutes
}

export interface Player {
  id: number;
  name: string;
  team: string;
  pos: Pos;
  cost: number;
  own: number;
  status: string;
  chance: number | null;
  news: string;
  back: string | null; // parsed expected return date (ISO) if the news gives one
  roles: { pen: number; cor: number; fk: number }; // set-piece rota strength: 1 first choice
  pts: number;
  mins: number;
  gw: number[];
  total: number;
  fx: Fixture[];
  form: FormMatch[];
}

export interface Meta {
  generated_at: string;
  season: string;
  gws: number[];
  model: string;
}

export interface PlayersFile extends Meta {
  players: Player[];
}

export interface TeamFixture {
  r: number;
  o: string;
  h: boolean;
  gf: number; // expected goals for
  ga: number; // expected goals against
}

export interface Team {
  team: string;
  name: string;
  fx: TeamFixture[];
}

export interface TeamsFile extends Meta {
  teams: Team[];
}
