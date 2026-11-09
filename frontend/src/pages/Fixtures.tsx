import { useEffect, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { api, type Match } from "../api";
import { useAsync } from "../hooks";
import { ErrorBox, MatchCard, Spinner } from "../components/ui";

const PAGE = 24;

export default function Fixtures() {
  const code = (useParams().code ?? "K1").toUpperCase();
  const [params, setParams] = useSearchParams();
  const teamId = params.get("team") ? Number(params.get("team")) : undefined;
  const round = params.get("round") ? Number(params.get("round")) : undefined;
  // Default view is upcoming matches; "all" shows the full season incl. results.
  const upcoming = params.get("view") !== "all";

  const teams = useAsync(() => api.teams(code), [code]);
  const [matches, setMatches] = useState<Match[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  const load = async (offset: number) => {
    setLoading(true);
    setError(null);
    try {
      const page = await api.matches(code, { team_id: teamId, round, upcoming, limit: PAGE, offset });
      setMatches((prev) => (offset === 0 ? page : [...prev, ...page]));
      setHasMore(page.length === PAGE);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    setMatches([]);
    load(0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [code, teamId, round, upcoming, attempt]);

  const setParam = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value); else next.delete(key);
    setParams(next, { replace: true });
  };

  // Double round-robin: each club plays every other club twice.
  const rounds = teams.data ? (teams.data.length - 1) * 2 : 0;

  return (
    <section>
      <div className="page-head">
        <h1>Fixtures</h1>
        <div className="filters">
          <div className="segmented" role="group" aria-label="Show">
            <button className={upcoming ? "active" : ""} onClick={() => setParam("view", "")}>Upcoming</button>
            <button className={!upcoming ? "active" : ""} onClick={() => setParam("view", "all")}>All</button>
          </div>
          <select aria-label="Team" value={teamId ?? ""} onChange={(e) => setParam("team", e.target.value)}>
            <option value="">All clubs</option>
            {teams.data?.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
          </select>
          <select aria-label="Round" value={round ?? ""} onChange={(e) => setParam("round", e.target.value)}>
            <option value="">All rounds</option>
            {Array.from({ length: rounds }, (_, i) => i + 1).map((r) => (
              <option key={r} value={r}>Round {r}</option>
            ))}
          </select>
        </div>
      </div>

      {error && <ErrorBox message={error} onRetry={() => setAttempt((a) => a + 1)} />}
      {!loading && !error && matches.length === 0 && (
        <p className="empty">No matches found. {upcoming && "Try showing all matches."}</p>
      )}
      <div className="match-grid">
        {matches.map((m) => <MatchCard key={m.id} match={m} />)}
      </div>
      {loading && <Spinner />}
      {!loading && hasMore && (
        <div className="center">
          <button className="btn btn-ghost" onClick={() => load(matches.length)}>Load more</button>
        </div>
      )}
    </section>
  );
}
