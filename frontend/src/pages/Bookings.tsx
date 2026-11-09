import { useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import { api, type Booking } from "../api";
import { useAsync } from "../hooks";
import { formatDateTime, formatKickoff, formatKRW } from "../format";
import { ErrorBox, Spinner, StatusBadge } from "../components/ui";

const CANCEL_CUTOFF_HOURS = 2;

function canCancel(b: Booking): boolean {
  if (b.status !== "confirmed") return false;
  if (b.match.status === "finished") return false;
  if (b.match.status === "cancelled") return true;
  return Date.now() < new Date(b.match.kickoff).getTime() - CANCEL_CUTOFF_HOURS * 3600_000;
}

function useCancel(onDone: (b: Booking) => void) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const cancel = async (b: Booking) => {
    if (!confirm(`Cancel booking ${b.reference}? The seats will be released.`)) return;
    setBusy(true);
    setError(null);
    try { onDone(await api.cancelBooking(b.reference)); } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  };
  return { cancel, busy, error };
}

export function MyBookings() {
  const { data, error, loading, reload, setData } = useAsync(api.bookings, []);
  const { cancel, busy, error: cancelError } = useCancel((b) =>
    setData((list) => list?.map((x) => (x.id === b.id ? b : x)) ?? null),
  );
  const [showCancelled, setShowCancelled] = useState(false);

  const list = data?.filter((b) => showCancelled || b.status === "confirmed") ?? [];

  return (
    <section>
      <div className="page-head">
        <h1>My bookings</h1>
        <label className="check">
          <input type="checkbox" checked={showCancelled} onChange={(e) => setShowCancelled(e.target.checked)} /> Show cancelled
        </label>
      </div>
      {error && <ErrorBox message={error} onRetry={reload} />}
      {cancelError && <ErrorBox message={cancelError} />}
      {loading && <Spinner />}
      {data && list.length === 0 && (
        <p className="empty">No bookings yet. <Link to="/">Find a match →</Link></p>
      )}
      <div className="booking-list">
        {list.map((b) => (
          <div key={b.id} className={`card booking ${b.status}`}>
            <div className="booking-main">
              <Link to={`/bookings/${b.reference}`} className="ref">{b.reference}</Link>
              <StatusBadge status={b.status} />
              <div className="booking-match">
                <strong>{b.match.home_team.name} vs {b.match.away_team.name}</strong>
                <span className="muted">{formatKickoff(b.match.kickoff)} · {b.match.stadium.name}</span>
              </div>
            </div>
            <div className="booking-side">
              <span>{b.quantity} × {b.zone.name}</span>
              <strong>{formatKRW(b.total_price)}</strong>
              {canCancel(b) && (
                <button className="btn btn-ghost btn-small" disabled={busy} onClick={() => cancel(b)}>Cancel</button>
              )}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

export function BookingDetail() {
  const ref = useParams().reference ?? "";
  const justBooked = (useLocation().state as { justBooked?: boolean } | null)?.justBooked;
  const { data: b, error, loading, reload, setData } = useAsync(() => api.booking(ref), [ref]);
  const { cancel, busy, error: cancelError } = useCancel((x) => setData(x));

  if (loading && !b) return <Spinner />;
  if (error && !b) return <ErrorBox message={error} onRetry={reload} />;
  if (!b) return null;

  return (
    <section>
      <Link to="/bookings" className="back">← My bookings</Link>
      {justBooked && b.status === "confirmed" && <div className="alert alert-success">🎉 You're going! Your booking is confirmed.</div>}
      <div className={`card ticket ${b.status}`}>
        <div className="ticket-head">
          <div>
            <span className="muted small">Booking reference</span>
            <div className="ref big">{b.reference}</div>
          </div>
          <StatusBadge status={b.status} />
        </div>
        <h2>
          <Link to={`/matches/${b.match.id}`}>{b.match.home_team.name} vs {b.match.away_team.name}</Link>
        </h2>
        <dl className="details">
          <dt>League</dt><dd>{b.match.league_code} · Round {b.match.round}</dd>
          <dt>Kickoff</dt><dd>{formatKickoff(b.match.kickoff)}</dd>
          <dt>Stadium</dt><dd>{b.match.stadium.name}, {b.match.stadium.city}</dd>
          <dt>Zone</dt><dd>{b.zone.name}</dd>
          <dt>Tickets</dt><dd>{b.quantity} × {formatKRW(b.unit_price)}</dd>
          <dt>Total</dt><dd><strong>{formatKRW(b.total_price)}</strong></dd>
          <dt>Booked</dt><dd>{formatDateTime(b.created_at)}</dd>
          {b.cancelled_at && (<><dt>Cancelled</dt><dd>{formatDateTime(b.cancelled_at)}</dd></>)}
        </dl>
        {cancelError && <ErrorBox message={cancelError} />}
        {canCancel(b) && (
          <button className="btn btn-danger" disabled={busy} onClick={() => cancel(b)}>
            {busy ? "Cancelling…" : "Cancel booking"}
          </button>
        )}
      </div>
    </section>
  );
}
