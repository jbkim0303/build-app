from datetime import datetime, timedelta, timezone

from app.models import Match, SeatZone


def first_upcoming(client):
    matches = client.get("/api/leagues/K1/matches", params={"upcoming": True, "limit": 1}).json()
    return client.get(f"/api/matches/{matches[0]['id']}").json()


def test_league_and_teams(client):
    leagues = client.get("/api/leagues").json()
    assert leagues[0]["code"] == "K1"
    teams = client.get("/api/leagues/k1/teams").json()
    assert len(teams) == 12
    assert client.get("/api/leagues/XX/teams").status_code == 404


def test_fixtures_double_round_robin(client):
    matches = client.get("/api/leagues/K1/matches", params={"limit": 500}).json()
    assert len(matches) == 12 * 11  # each pair meets home and away
    pairs = {(m["home_team"]["id"], m["away_team"]["id"]) for m in matches}
    assert len(pairs) == 132
    rounds = {m["round"] for m in matches}
    assert rounds == set(range(1, 23))


def test_standings(client):
    rows = client.get("/api/leagues/K1/standings").json()
    assert len(rows) == 12
    assert all(r["played"] == 3 for r in rows)
    assert rows == sorted(rows, key=lambda r: (-r["points"], -r["goals_for"], -r["goal_difference"], r["team"]["name"]))


def test_auth_flow(client):
    r = client.post("/api/auth/register", json={"email": "A@B.com", "name": "A", "password": "short"})
    assert r.status_code == 422
    r = client.post("/api/auth/register", json={"email": "A@B.com", "name": "A", "password": "longenough"})
    assert r.status_code == 201 and r.json()["email"] == "a@b.com"
    assert client.post("/api/auth/register", json={"email": "a@b.com", "name": "A", "password": "longenough"}).status_code == 409
    assert client.post("/api/auth/login", data={"username": "a@b.com", "password": "wrong"}).status_code == 401
    assert client.get("/api/bookings").status_code == 401


def test_book_and_cancel(client, user_headers):
    match = first_upcoming(client)
    zone = match["zones"][0]
    r = client.post("/api/bookings", json={"zone_id": zone["id"], "quantity": 3}, headers=user_headers)
    assert r.status_code == 201, r.text
    booking = r.json()
    assert booking["reference"].startswith("K1-")
    assert booking["total_price"] == zone["price"] * 3
    assert booking["zone"]["available"] == zone["available"] - 3

    assert len(client.get("/api/bookings", headers=user_headers).json()) == 1
    r = client.post(f"/api/bookings/{booking['reference']}/cancel", headers=user_headers)
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    assert r.json()["zone"]["available"] == zone["available"]
    assert client.post(f"/api/bookings/{booking['reference']}/cancel", headers=user_headers).status_code == 409


def test_cannot_oversell(client, db, user_headers):
    match = first_upcoming(client)
    zone_id = match["zones"][0]["id"]
    zone = db.get(SeatZone, zone_id)
    zone.sold = zone.capacity - 2
    db.commit()
    assert client.post("/api/bookings", json={"zone_id": zone_id, "quantity": 3}, headers=user_headers).status_code == 409
    assert client.post("/api/bookings", json={"zone_id": zone_id, "quantity": 2}, headers=user_headers).status_code == 201
    assert client.post("/api/bookings", json={"zone_id": zone_id, "quantity": 1}, headers=user_headers).status_code == 409


def test_ticket_limit(client, user_headers):
    zone_id = first_upcoming(client)["zones"][0]["id"]
    assert client.post("/api/bookings", json={"zone_id": zone_id, "quantity": 9}, headers=user_headers).status_code == 422


def test_cannot_book_past_match(client, user_headers):
    past = client.get("/api/leagues/K1/matches", params={"status": "finished", "limit": 1}).json()[0]
    zone_id = client.get(f"/api/matches/{past['id']}").json()["zones"][0]["id"]
    assert client.post("/api/bookings", json={"zone_id": zone_id, "quantity": 1}, headers=user_headers).status_code == 409


def test_cancel_cutoff(client, db, user_headers):
    match = first_upcoming(client)
    r = client.post("/api/bookings", json={"zone_id": match["zones"][0]["id"], "quantity": 1}, headers=user_headers)
    ref = r.json()["reference"]
    m = db.get(Match, match["id"])
    m.kickoff = datetime.now(timezone.utc) + timedelta(minutes=30)
    db.commit()
    assert client.post(f"/api/bookings/{ref}/cancel", headers=user_headers).status_code == 409


def test_bookings_are_private(client, user_headers, other_headers):
    zone_id = first_upcoming(client)["zones"][0]["id"]
    ref = client.post("/api/bookings", json={"zone_id": zone_id, "quantity": 1}, headers=user_headers).json()["reference"]
    assert client.get(f"/api/bookings/{ref}", headers=other_headers).status_code == 404
    assert client.post(f"/api/bookings/{ref}/cancel", headers=other_headers).status_code == 404
    assert client.get(f"/api/bookings/{ref}", headers=user_headers).status_code == 200


def test_admin_create_match_and_cancel(client, user_headers, admin_headers):
    teams = client.get("/api/leagues/K1/teams").json()
    body = {
        "league_id": 1, "round": 23, "home_team_id": teams[0]["id"], "away_team_id": teams[1]["id"],
        "kickoff": (datetime.now(timezone.utc) + timedelta(days=60)).isoformat(),
        "zones": [{"name": "Family", "price": 10000, "capacity": 100}],
    }
    assert client.post("/api/admin/matches", json=body, headers=user_headers).status_code == 403
    r = client.post("/api/admin/matches", json=body, headers=admin_headers)
    assert r.status_code == 201, r.text
    match = r.json()
    assert match["stadium"]["id"] == teams[0]["home_stadium"]["id"]
    zone_id = match["zones"][0]["id"]

    ref = client.post("/api/bookings", json={"zone_id": zone_id, "quantity": 4}, headers=user_headers).json()["reference"]
    r = client.post(f"/api/admin/matches/{match['id']}/cancel", headers=admin_headers)
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    assert client.get(f"/api/bookings/{ref}", headers=user_headers).json()["status"] == "cancelled"
    # No result can be recorded for a future match.
    assert client.post(f"/api/admin/matches/{match['id']}/result", json={"home_score": 1, "away_score": 0},
                       headers=admin_headers).status_code == 409
