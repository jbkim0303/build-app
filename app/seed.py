"""Sample K League data: leagues, teams, stadiums and double round-robin fixture lists.

The club lists are illustrative sample data — edit LEAGUES to match the real season.
"""
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .models import League, Match, MatchStatus, SeatZone, Stadium, Team, User
from .security import hash_password

# (club, short name, city, stadium, stadium capacity)
K1_TEAMS = [
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

K2_TEAMS = [
    ("Suwon Samsung Bluewings", "SSB", "Suwon", "Suwon World Cup Stadium", 43959),
    ("Busan IPark", "BUS", "Busan", "Busan Gudeok Stadium", 12349),
    ("Jeonnam Dragons", "JND", "Gwangyang", "Gwangyang Football Stadium", 13496),
    ("Bucheon FC 1995", "BUC", "Bucheon", "Bucheon Stadium", 34456),
    ("Seoul E-Land FC", "SEL", "Seoul", "Mokdong Stadium", 15511),
    ("Seongnam FC", "SNG", "Seongnam", "Tancheon Stadium", 16146),
    ("Gyeongnam FC", "GYE", "Changwon", "Changwon Football Center", 15116),
    ("Chungnam Asan FC", "ASA", "Asan", "Yi Sun-sin Stadium", 19283),
    ("Ansan Greeners", "ANS", "Ansan", "Ansan Wa~ Stadium", 35000),
    ("Gimpo FC", "GMP", "Gimpo", "Gimpo Solteo Football Stadium", 5076),
    ("Chungbuk Cheongju FC", "CHE", "Cheongju", "Cheongju Stadium", 15000),
    ("Cheonan City FC", "CHN", "Cheonan", "Cheonan Stadium", 26000),
    ("Hwaseong FC", "HWA", "Hwaseong", "Hwaseong Stadium", 35270),
    ("Daegu FC", "DGU", "Daegu", "DGB Daegu Bank Park", 12415),
]

# (zone name, base price in KRW, share of stadium capacity put on sale)
ZONE_TEMPLATE = [
    ("VIP", 60000, 0.01),
    ("Premium", 35000, 0.09),
    ("Home Supporters", 15000, 0.15),
    ("Away Supporters", 15000, 0.05),
    ("General Admission", 20000, 0.30),
]


@dataclass(frozen=True)
class LeagueSpec:
    code: str
    name: str
    teams: list
    price_factor: float  # multiplier on ZONE_TEMPLATE prices
    kickoff_weekday: int  # 0 = Monday
    kickoff_utc: tuple[int, int]  # (hour, minute)


LEAGUES = [
    # Saturday 19:00 KST
    LeagueSpec("K1", "K League 1", K1_TEAMS, 1.0, 5, (10, 0)),
    # Sunday 16:30 KST, second-division tickets are cheaper
    LeagueSpec("K2", "K League 2", K2_TEAMS, 0.6, 6, (7, 30)),
]
LEAGUE_SPECS = {spec.code: spec for spec in LEAGUES}


def default_zones(stadium_capacity: int, league_code: str = "K1") -> list[SeatZone]:
    spec = LEAGUE_SPECS.get(league_code)
    factor = spec.price_factor if spec else 1.0
    return [
        # round to the nearest 1,000 KRW
        SeatZone(name=name, price=int(round(price * factor, -3)), capacity=max(10, int(stadium_capacity * share)))
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


def _next_kickoff(now: datetime, weekday: int, hour: int, minute: int) -> datetime:
    days = (weekday - now.weekday()) % 7 or 7
    return (now + timedelta(days=days)).replace(hour=hour, minute=minute, second=0, microsecond=0)


def seed_league(db: Session, spec: LeagueSpec, played_rounds: int, rng: random.Random) -> None:
    now = datetime.now(timezone.utc)
    league = League(code=spec.code, name=spec.name, country="South Korea", season=now.year)
    db.add(league)
    teams = []
    for name, short, city, stadium_name, capacity in spec.teams:
        stadium = Stadium(name=stadium_name, city=city, capacity=capacity)
        team = Team(league=league, name=name, short_name=short, city=city, home_stadium=stadium)
        db.add(team)
        teams.append(team)
    db.flush()

    by_id = {t.id: t for t in teams}
    # Rounds are a week apart. The first `played_rounds` rounds are in the past
    # with results so the standings have data.
    start = _next_kickoff(now, spec.kickoff_weekday, *spec.kickoff_utc) - timedelta(weeks=played_rounds)
    for rnd_index, pairs in enumerate(round_robin([t.id for t in teams])):
        kickoff = start + timedelta(weeks=rnd_index)
        for home_id, away_id in pairs:
            home = by_id[home_id]
            match = Match(
                league=league, round=rnd_index + 1, home_team_id=home_id, away_team_id=away_id,
                stadium_id=home.home_stadium_id, kickoff=kickoff,
                zones=default_zones(home.home_stadium.capacity, spec.code),
            )
            if rnd_index < played_rounds:
                match.status = MatchStatus.finished
                match.home_score, match.away_score = rng.randint(0, 4), rng.randint(0, 3)
            db.add(match)


def seed(db: Session, played_rounds: int = 3, rng_seed: int = 2026) -> None:
    """Idempotent: creates the admin user and any league in LEAGUES that is missing,
    so adding a league here also adds it to an existing database on next start."""
    if not db.scalar(select(User).where(User.email == settings.admin_email)):
        db.add(User(email=settings.admin_email, name="Admin",
                    password_hash=hash_password(settings.admin_password), is_admin=True))
    rng = random.Random(rng_seed)
    for spec in LEAGUES:
        if not db.scalar(select(League).where(League.code == spec.code)):
            seed_league(db, spec, played_rounds, rng)
    db.commit()
