import { Link } from "react-router-dom";
import type { Match, MatchStatus } from "../api";
import { formatKickoff } from "../format";

export function Spinner() {
  return <div className="spinner" role="status" aria-label="Loading" />;
}

export function ErrorBox({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="alert alert-error" role="alert">
      <span>{message}</span>
      {onRetry && <button className="btn btn-small" onClick={onRetry}>Retry</button>}
    </div>
  );
}

export function StatusBadge({ status }: { status: MatchStatus | "confirmed" }) {
  return <span className={`badge badge-${status}`}>{status}</span>;
}

export function Score({ match }: { match: Match }) {
  if (match.status === "finished") {
    return <span className="score">{match.home_score} – {match.away_score}</span>;
  }
  return <span className="score score-vs">vs</span>;
}

export function MatchCard({ match }: { match: Match }) {
  return (
    <Link to={`/matches/${match.id}`} className={`match-card match-${match.status}`}>
      <div className="match-meta">
        <span>Round {match.round}</span>
        <span>{formatKickoff(match.kickoff)}</span>
      </div>
      <div className="match-teams">
        <span className="team team-home">{match.home_team.name}</span>
        <Score match={match} />
        <span className="team team-away">{match.away_team.name}</span>
      </div>
      <div className="match-meta">
        <span>{match.stadium.name}</span>
        {match.status === "scheduled" ? <span className="cta">Tickets →</span> : <StatusBadge status={match.status} />}
      </div>
    </Link>
  );
}
