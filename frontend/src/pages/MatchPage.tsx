import { useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, type MatchDetail } from "../api";
import { useAuth } from "../auth";
import { useAsync } from "../hooks";
import { formatKickoff, formatKRW } from "../format";
import { ErrorBox, Score, Spinner, StatusBadge } from "../components/ui";

const MAX_TICKETS = 8;

export default function MatchPage() {
  const id = Number(useParams().id);
  const { data: match, error, loading, reload, setData } = useAsync(() => api.match(id), [id]);

  if (loading && !match) return <Spinner />;
  if (error && !match) return <ErrorBox message={error} onRetry={reload} />;
  if (!match) return null;

  const salesOpen = match.status === "scheduled" && new Date(match.kickoff) > new Date();

  return (
    <section>
      <Link to={`/leagues/${match.league_code}`} className="back">← {match.league_code} fixtures</Link>
      <div className="card hero">
        <div className="match-meta">
          <span>{match.league_code} · Round {match.round}</span>
          <StatusBadge status={match.status} />
        </div>
        <div className="match-teams big">
          <span className="team team-home">{match.home_team.name}</span>
          <Score match={match} />
          <span className="team team-away">{match.away_team.name}</span>
        </div>
        <div className="hero-info">
          <span>📅 {formatKickoff(match.kickoff)}</span>
          <span>🏟️ {match.stadium.name}, {match.stadium.city}</span>
        </div>
      </div>

      {salesOpen ? (
        <BookingPanel match={match} onBooked={reload} />
      ) : (
        <div className="alert">
          {match.status === "cancelled" ? "This match was cancelled. All bookings were voided." : "Ticket sales for this match are closed."}
        </div>
      )}

      <AdminPanel match={match} onChange={setData} />
    </section>
  );
}

function BookingPanel({ match, onBooked }: { match: MatchDetail; onBooked: () => void }) {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [zoneId, setZoneId] = useState<number | null>(null);
  const [quantity, setQuantity] = useState(1);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const zone = match.zones.find((z) => z.id === zoneId) ?? null;
  const maxQty = zone ? Math.min(MAX_TICKETS, zone.available) : MAX_TICKETS;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!zone) return;
    if (!user) {
      navigate("/login", { state: { from: `/matches/${match.id}` } });
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const booking = await api.book(zone.id, quantity);
      navigate(`/bookings/${booking.reference}`, { state: { justBooked: true } });
    } catch (err) {
      setError((err as Error).message);
      onBooked(); // refresh availability
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="card" onSubmit={submit}>
      <h2>Choose your seats</h2>
      <div className="zones">
        {match.zones.map((z) => {
          const soldOut = z.available === 0;
          const pct = Math.round(((z.capacity - z.available) / z.capacity) * 100);
          return (
            <label key={z.id} className={`zone ${zoneId === z.id ? "selected" : ""} ${soldOut ? "sold-out" : ""}`}>
              <input
                type="radio"
                name="zone"
                value={z.id}
                disabled={soldOut}
                checked={zoneId === z.id}
                onChange={() => { setZoneId(z.id); setQuantity((q) => Math.min(q, Math.max(1, Math.min(MAX_TICKETS, z.available)))); }}
              />
              <span className="zone-name">{z.name}</span>
              <span className="zone-price">{formatKRW(z.price)}</span>
              <span className="zone-avail">
                {soldOut ? "Sold out" : `${z.available.toLocaleString()} of ${z.capacity.toLocaleString()} left`}
              </span>
              <span className="bar"><span style={{ width: `${pct}%` }} /></span>
            </label>
          );
        })}
      </div>

      <div className="checkout">
        <label className="qty">
          Tickets
          <select value={quantity} onChange={(e) => setQuantity(Number(e.target.value))} disabled={!zone}>
            {Array.from({ length: Math.max(1, maxQty) }, (_, i) => i + 1).map((n) => <option key={n}>{n}</option>)}
          </select>
        </label>
        <div className="total">
          <span className="muted">Total</span>
          <strong>{zone ? formatKRW(zone.price * quantity) : "—"}</strong>
        </div>
        <button className="btn btn-primary" disabled={!zone || busy}>
          {busy ? "Booking…" : user ? "Book tickets" : "Log in to book"}
        </button>
      </div>
      {error && <ErrorBox message={error} />}
      <p className="muted small">Up to {MAX_TICKETS} tickets per booking. Free cancellation until 2 hours before kickoff.</p>
    </form>
  );
}

function AdminPanel({ match, onChange }: { match: MatchDetail; onChange: (m: MatchDetail) => void }) {
  const { user } = useAuth();
  const [home, setHome] = useState(match.home_score ?? 0);
  const [away, setAway] = useState(match.away_score ?? 0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!user?.is_admin || match.status === "cancelled") return null;

  const run = async (fn: () => Promise<MatchDetail>) => {
    setBusy(true);
    setError(null);
    try { onChange(await fn()); } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  };

  const kickedOff = new Date(match.kickoff) <= new Date();

  return (
    <div className="card admin">
      <h2>Admin</h2>
      <div className="admin-row">
        <span>Final score</span>
        <input type="number" min={0} value={home} onChange={(e) => setHome(Number(e.target.value))} aria-label="Home score" />
        <span>–</span>
        <input type="number" min={0} value={away} onChange={(e) => setAway(Number(e.target.value))} aria-label="Away score" />
        <button className="btn btn-small" disabled={busy || !kickedOff} title={kickedOff ? "" : "Match has not kicked off yet"}
          onClick={() => run(() => api.recordResult(match.id, home, away))}>
          Save result
        </button>
      </div>
      {match.status === "scheduled" && (
        <button className="btn btn-danger btn-small" disabled={busy}
          onClick={() => confirm("Cancel this match and void every booking for it?") && run(() => api.cancelMatch(match.id))}>
          Cancel match
        </button>
      )}
      {error && <ErrorBox message={error} />}
    </div>
  );
}
