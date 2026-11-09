"""Sample K League 1 data: teams, stadiums and a double round-robin fixture list.

The club list is illustrative sample data — edit TEAMS to match the real season.
"""
import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .models import League, Match, MatchStatus, SeatZone, Stadium, Team, User
from .security import hash_password

# (club, short name, city, stadium, stadium capacity)
TEAMS = [
    ("Ulsan HD FC", "ULS", "Ulsan", "Ulsan Munsu Football Stadium", 37897),
    ("Jeonbuk Hyundai Motors", "JEO", "Jeonju", "Jeonju World Cup Stadium", 36781),
    ("Pohang Steelers", "POH", "Pohang", "Pohang Steelyard", 15521),
    ("FC Seoul", "SEO", "Seoul", "Seoul World Cup Stadium", 66704),
    ("Gangwon FC", "GAN", "Gangneung", "Gangneung Stadium", 22333),
    ("Gimcheon Sangmu", "GIM", "Gimcheon", "Gimcheon Stadium", 25000),
    ("Suwon FC", "SUW", "Suwon", "Suwon Sports Complex", 11808),
    ("Jeju SK FC", "JEJ", "Seogwipo", "Jeju World Cup Stadium", 29791),
    ("Daejeon Hana Citizen", "DAE", "Daejeon", "Daejeon World Cup Stadium", 40535),
    ("Gwangju FC", "GWA", "Gwangju", "Gwangju Football Stadium", 10007),
    ("FC Anyang", "ANY", "Anyang", "Anyang Stadium", 17143),
    ("Incheon United", "INC", "Incheon", "Incheon Football Stadium", 20891),
]

# (zone name, price in KRW, share of stadium capacity put on sale)
ZONE_TEMPLATE = [
    ("VIP", 60000, 0.01),
    ("Premium", 35000, 0.09),
    ("Home Supporters", 15000, 0.15),
    ("Away Supporters", 15000, 0.05),
    ("General Admission", 20000, 0.30),
]


def default_zones(stadium_capacity: int) -> list[SeatZone]:
    return [
        SeatZone(name=name, price=price, capacity=max(10, int(stadium_capacity * share)))
        for name, price, share in ZONE_TEMPLATE
    ]


def round_robin(team_ids: list[int]) -> list[list[tuple[int, int]]]:
    """Circle-method double round robin; returns rounds of (home, away) pairs."""
    ids = list(team_ids)
    if len(ids) % 2:
        ids.append(None)
    n = len(ids)
    first_half = []
    for r in range(n - 1):
        pairs = []
        for i in range(n // 2):
            a, b = ids[i], ids[n - 1 - i]
            if a is not None and b is not None:
                pairs.append((a, b) if (r + i) % 2 == 0 else (b, a))
        first_half.append(pairs)
        ids = [ids[0], ids[-1], *ids[1:-1]]
    second_half = [[(b, a) for a, b in rnd] for rnd in first_half]
    return first_half + second_half


def seed(db: Session, played_rounds: int = 3, rng_seed: int = 2026) -> None:
    """Idempotent: does nothing if the K1 league already exists."""
    if not db.scalar(select(User).where(User.email == settings.admin_email)):
        db.add(User(email=settings.admin_email, name="Admin",
                    password_hash=hash_password(settings.admin_password), is_admin=True))

    if db.scalar(select(League).where(League.code == "K1")):
        db.commit()
        return

    now = datetime.now(timezone.utc)
    league = League(code="K1", name="K League 1", country="South Korea", season=now.year)
    db.add(league)
    teams = []
    for name, short, city, stadium_name, capacity in TEAMS:
        stadium = Stadium(name=stadium_name, city=city, capacity=capacity)
        team = Team(league=league, name=name, short_name=short, city=city, home_stadium=stadium)
        db.add(team)
        teams.append(team)
    db.flush()

    rng = random.Random(rng_seed)
    by_id = {t.id: t for t in teams}
    # Rounds are a week apart, Saturday 19:00 KST (10:00 UTC). The first
    # `played_rounds` rounds are in the past with results so standings have data.
    days_to_sat = (5 - now.weekday()) % 7 or 7
    next_saturday = (now + timedelta(days=days_to_sat)).replace(hour=10, minute=0, second=0, microsecond=0)
    start = next_saturday - timedelta(weeks=played_rounds)

    for rnd_index, pairs in enumerate(round_robin([t.id for t in teams])):
        kickoff = start + timedelta(weeks=rnd_index)
        for home_id, away_id in pairs:
            home = by_id[home_id]
            match = Match(league=league, round=rnd_index + 1, home_team_id=home_id, away_team_id=away_id,
                          stadium_id=home.home_stadium_id, kickoff=kickoff, zones=default_zones(home.home_stadium.capacity))
            if rnd_index < played_rounds:
                match.status = MatchStatus.finished
                match.home_score, match.away_score = rng.randint(0, 4), rng.randint(0, 3)
            db.add(match)
    db.commit()
