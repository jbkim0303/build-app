# Football League Booking API

A Python (FastAPI + SQLAlchemy) backend for booking football match tickets.
It ships with **K League 1** sample data: 12 clubs, their home stadiums, and a full
double round-robin fixture list (22 rounds / 132 matches).

## Features

- **Auth**: register, log in (OAuth2 password flow, JWT bearer tokens), `/me`
- **League data**: leagues, teams, fixtures (filter by team, round, status, date, upcoming), live standings
- **Ticket booking**: each match has seat zones (VIP, Premium, Home/Away Supporters, General) with price and capacity
  - atomic seat reservation (can't oversell, even with concurrent requests)
  - max tickets per booking (default 8)
  - no booking after kickoff or for finished or cancelled matches
  - cancellation up to 2h before kickoff, which frees the seats again
  - bookings are visible only to their owner (and admins)
- **Admin**: create matches (zones default to the home stadium's size), record results, cancel a match (voids all of its bookings)

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
```

Open http://localhost:8000/docs for the interactive Swagger UI.
On first start the database (`league.db`, SQLite) is created and seeded, along with an admin
account `admin@league.local` / `admin1234`. Change it with `ADMIN_EMAIL` / `ADMIN_PASSWORD`.

### Example

```bash
# register + log in
curl -X POST localhost:8000/api/auth/register -H 'Content-Type: application/json' \
  -d '{"email":"fan@example.com","name":"Fan","password":"password123"}'
TOKEN=$(curl -s -X POST localhost:8000/api/auth/login \
  -d 'username=fan@example.com&password=password123' | python -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')

# find a match and its seat zones
curl 'localhost:8000/api/leagues/K1/matches?upcoming=true&limit=5'
curl localhost:8000/api/matches/19

# book 2 tickets in zone 91
curl -X POST localhost:8000/api/bookings -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d '{"zone_id":91,"quantity":2}'
```

## API overview

| Method | Path | Description |
|---|---|---|
| POST | `/api/auth/register` | Create an account |
| POST | `/api/auth/login` | Get a bearer token (form: `username`, `password`) |
| GET | `/api/auth/me` | Current user |
| GET | `/api/leagues` | List leagues |
| GET | `/api/leagues/{code}/teams` | Teams with home stadiums |
| GET | `/api/leagues/{code}/matches` | Fixtures (`team_id`, `round`, `status`, `date_from`, `date_to`, `upcoming`, `limit`, `offset`) |
| GET | `/api/leagues/{code}/standings` | League table (points, then goals scored, then goal difference) |
| GET | `/api/matches/{id}` | Match detail with seat zones and availability |
| POST | `/api/bookings` | Book tickets `{zone_id, quantity}` |
| GET | `/api/bookings` | My bookings |
| GET | `/api/bookings/{reference}` | Booking detail |
| POST | `/api/bookings/{reference}/cancel` | Cancel a booking |
| POST | `/api/admin/matches` | Create a match (admin) |
| POST | `/api/admin/matches/{id}/result` | Record a final score (admin) |
| POST | `/api/admin/matches/{id}/cancel` | Cancel a match and its bookings (admin) |

## Configuration (environment variables)

| Variable | Default |
|---|---|
| `DATABASE_URL` | `sqlite:///./league.db` (any SQLAlchemy URL, e.g. PostgreSQL) |
| `SECRET_KEY` | dev placeholder. **Set this in production.** |
| `TOKEN_EXPIRE_MINUTES` | `1440` |
| `MAX_TICKETS_PER_BOOKING` | `8` |
| `CANCEL_CUTOFF_HOURS` | `2` |
| `SEED_ON_STARTUP` | `1` |

## Project layout

```
app/
  main.py        FastAPI app and startup (create tables + seed)
  models.py      SQLAlchemy models: League, Stadium, Team, Match, SeatZone, Booking, User
  schemas.py     Pydantic request and response models
  seed.py        K League 1 sample data + round-robin fixture generator
  security.py    password hashing (PBKDF2) and JWT
  routers/       auth, league, bookings, admin
tests/           pytest suite
```

Run the tests with `pytest`.

> The club and stadium data is sample data. Edit `TEAMS` in `app/seed.py` to match the real season.
> To add another league (e.g. K League 2), insert a `League` with a new `code` and its teams. Every endpoint is keyed by league code.
