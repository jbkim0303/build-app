# Frontend

React 19 + TypeScript + Vite single-page app for the booking API.

## Pages

| Route | What it does |
|---|---|
| `/leagues/:code` | Fixtures for K1 / K2: upcoming or full season, filter by club and round, "load more" paging |
| `/leagues/:code/standings` | League table |
| `/matches/:id` | Match detail, seat zones with live availability, ticket booking; admins can record a result or cancel the match |
| `/login`, `/register` | Account forms (JWT stored in `localStorage`) |
| `/bookings` | My bookings, with cancellation while it is still allowed |
| `/bookings/:reference` | Ticket / booking detail |

## Development

Run the API on port 8000 (from the repo root: `uvicorn app.main:app --reload`), then:

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173, /api is proxied to :8000
```

Set `API_URL` to proxy to a different backend, e.g. `API_URL=http://localhost:9000 npm run dev`.

## Production

```bash
npm run build      # outputs frontend/dist
```

When `frontend/dist` exists, the FastAPI app serves it at `/` (with an `index.html` fallback for
client-side routes), so `uvicorn app.main:app` serves the API and the UI from one origin.
