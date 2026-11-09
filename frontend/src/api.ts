// Typed client for the FastAPI backend (see app/schemas.py).

export type MatchStatus = "scheduled" | "finished" | "cancelled";
export type BookingStatus = "confirmed" | "cancelled";

export interface User { id: number; email: string; name: string; is_admin: boolean }
export interface League { id: number; code: string; name: string; country: string; season: number }
export interface Stadium { id: number; name: string; city: string; capacity: number }
export interface TeamBrief { id: number; name: string; short_name: string }
export interface Team extends TeamBrief { city: string; home_stadium: Stadium }
export interface SeatZone { id: number; name: string; price: number; capacity: number; available: number }
export interface Match {
  id: number;
  league_code: string;
  round: number;
  kickoff: string;
  status: MatchStatus;
  home_team: TeamBrief;
  away_team: TeamBrief;
  stadium: Stadium;
  home_score: number | null;
  away_score: number | null;
}
export interface MatchDetail extends Match { zones: SeatZone[] }
export interface StandingRow {
  position: number;
  team: TeamBrief;
  played: number;
  won: number;
  drawn: number;
  lost: number;
  goals_for: number;
  goals_against: number;
  goal_difference: number;
  points: number;
}
export interface Booking {
  id: number;
  reference: string;
  quantity: number;
  unit_price: number;
  total_price: number;
  status: BookingStatus;
  created_at: string;
  cancelled_at: string | null;
  zone: SeatZone;
  match: Match;
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

const TOKEN_KEY = "league.token";

export const tokenStore = {
  get: (): string | null => {
    try { return localStorage.getItem(TOKEN_KEY); } catch { return null; }
  },
  set: (t: string | null) => {
    try { t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY); } catch { /* ignore */ }
  },
};

/** Called when the API rejects our token, so the auth context can log out. */
let onUnauthorized: () => void = () => {};
export function setUnauthorizedHandler(fn: () => void) { onUnauthorized = fn; }

function errorMessage(body: unknown, fallback: string): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;
  // FastAPI validation errors: [{loc, msg, ...}]
  if (Array.isArray(detail)) return detail.map((d) => d?.msg ?? String(d)).join("; ");
  return fallback;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const token = tokenStore.get();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && typeof init.body === "string") headers.set("Content-Type", "application/json");

  const res = await fetch(path, { ...init, headers });
  const body = res.status === 204 ? null : await res.json().catch(() => null);
  if (!res.ok) {
    if (res.status === 401 && token) onUnauthorized();
    throw new ApiError(res.status, errorMessage(body, `${res.status} ${res.statusText}`));
  }
  return body as T;
}

const json = (data: unknown): RequestInit => ({ method: "POST", body: JSON.stringify(data) });

export interface MatchFilters {
  team_id?: number;
  round?: number;
  status?: MatchStatus;
  upcoming?: boolean;
  limit?: number;
  offset?: number;
}

function qs(params: object): string {
  const s = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== "" && v !== false) s.set(k, String(v));
  const str = s.toString();
  return str ? `?${str}` : "";
}

export const api = {
  register: (email: string, name: string, password: string) =>
    request<User>("/api/auth/register", json({ email, name, password })),
  login: (email: string, password: string) =>
    request<{ access_token: string }>("/api/auth/login", {
      method: "POST",
      body: new URLSearchParams({ username: email, password }),
    }),
  me: () => request<User>("/api/auth/me"),

  leagues: () => request<League[]>("/api/leagues"),
  teams: (code: string) => request<Team[]>(`/api/leagues/${code}/teams`),
  matches: (code: string, f: MatchFilters = {}) => request<Match[]>(`/api/leagues/${code}/matches${qs(f)}`),
  standings: (code: string) => request<StandingRow[]>(`/api/leagues/${code}/standings`),
  match: (id: number) => request<MatchDetail>(`/api/matches/${id}`),

  book: (zone_id: number, quantity: number) => request<Booking>("/api/bookings", json({ zone_id, quantity })),
  bookings: () => request<Booking[]>("/api/bookings"),
  booking: (ref: string) => request<Booking>(`/api/bookings/${encodeURIComponent(ref)}`),
  cancelBooking: (ref: string) =>
    request<Booking>(`/api/bookings/${encodeURIComponent(ref)}/cancel`, { method: "POST" }),

  recordResult: (id: number, home_score: number, away_score: number) =>
    request<MatchDetail>(`/api/admin/matches/${id}/result`, json({ home_score, away_score })),
  cancelMatch: (id: number) => request<MatchDetail>(`/api/admin/matches/${id}/cancel`, { method: "POST" }),
};
