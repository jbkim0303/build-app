import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import { useAsync } from "../hooks";
import { ErrorBox, Spinner } from "../components/ui";

export default function Standings() {
  const code = (useParams().code ?? "K1").toUpperCase();
  const { data, error, loading, reload } = useAsync(() => api.standings(code), [code]);

  return (
    <section>
      <div className="page-head">
        <h1>Standings</h1>
        <p className="muted">Ranked by points, then goals scored, then goal difference.</p>
      </div>
      {error && <ErrorBox message={error} onRetry={reload} />}
      {loading && <Spinner />}
      {data && (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>#</th><th className="left">Club</th><th>P</th><th>W</th><th>D</th><th>L</th>
                <th className="hide-sm">GF</th><th className="hide-sm">GA</th><th>GD</th><th>Pts</th>
              </tr>
            </thead>
            <tbody>
              {data.map((r) => (
                <tr key={r.team.id}>
                  <td>{r.position}</td>
                  <td className="left">
                    <Link to={`/leagues/${code}?team=${r.team.id}&view=all`}>{r.team.name}</Link>
                  </td>
                  <td>{r.played}</td><td>{r.won}</td><td>{r.drawn}</td><td>{r.lost}</td>
                  <td className="hide-sm">{r.goals_for}</td><td className="hide-sm">{r.goals_against}</td>
                  <td>{r.goal_difference > 0 ? `+${r.goal_difference}` : r.goal_difference}</td>
                  <td><strong>{r.points}</strong></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
