import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { useAsync } from "../hooks";

export function currentLeague(pathname: string): string {
  const m = pathname.match(/^\/leagues\/([^/]+)/);
  return m ? m[1].toUpperCase() : "K1";
}

export default function Layout() {
  const { user, logout } = useAuth();
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const leagues = useAsync(api.leagues, []);
  const code = currentLeague(pathname);
  const onStandings = pathname.endsWith("/standings");

  return (
    <>
      <header className="topbar">
        <div className="container topbar-inner">
          <Link to="/" className="brand">⚽ K League Tickets</Link>
          <nav className="nav">
            <NavLink to={`/leagues/${code}`} end>Fixtures</NavLink>
            <NavLink to={`/leagues/${code}/standings`}>Standings</NavLink>
            {user && <NavLink to="/bookings">My bookings</NavLink>}
          </nav>
          <div className="user">
            {user ? (
              <>
                <span className="user-name" title={user.email}>
                  {user.name}{user.is_admin && <span className="badge badge-admin">admin</span>}
                </span>
                <button className="btn btn-ghost btn-small" onClick={() => { logout(); navigate("/"); }}>Log out</button>
              </>
            ) : (
              <>
                <Link to="/login" state={{ from: pathname }} className="btn btn-ghost btn-small">Log in</Link>
                <Link to="/register" className="btn btn-small">Sign up</Link>
              </>
            )}
          </div>
        </div>
        {pathname.startsWith("/leagues") && leagues.data && (
          <div className="container league-tabs">
            {leagues.data.map((l) => (
              <NavLink
                key={l.code}
                to={`/leagues/${l.code}${onStandings ? "/standings" : ""}`}
                className={() => (l.code === code ? "tab active" : "tab")}
              >
                {l.name} <small>{l.season}</small>
              </NavLink>
            ))}
          </div>
        )}
      </header>
      <main className="container">
        <Outlet />
      </main>
      <footer className="container footer">Sample data · Prices in KRW · Kickoff times in KST</footer>
    </>
  );
}

export function RequireAuth({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const { pathname } = useLocation();
  const navigate = useNavigate();
  if (loading) return null;
  if (!user) {
    return (
      <div className="card narrow center">
        <p>Please log in to see this page.</p>
        <button className="btn" onClick={() => navigate("/login", { state: { from: pathname } })}>Log in</button>
      </div>
    );
  }
  return <>{children}</>;
}
