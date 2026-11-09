from datetime import date, datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from ..database import get_db
from ..models import League, Match, MatchStatus, Team
from ..schemas import LeagueOut, MatchDetail, MatchOut, StandingRow, TeamBrief, TeamOut

router = APIRouter(prefix="/api", tags=["league"])


def _get_league(db: Session, code: str) -> League:
    league = db.scalar(select(League).where(League.code == code.upper()))
    if not league:
        raise HTTPException(404, f"League '{code}' not found")
    return league


@router.get("/leagues", response_model=list[LeagueOut])
def list_leagues(db: Session = Depends(get_db)):
    return db.scalars(select(League).order_by(League.id)).all()


@router.get("/leagues/{code}/teams", response_model=list[TeamOut])
def list_teams(code: str, db: Session = Depends(get_db)):
    league = _get_league(db, code)
    return db.scalars(
        select(Team).where(Team.league_id == league.id).options(selectinload(Team.home_stadium)).order_by(Team.name)
    ).all()


@router.get("/leagues/{code}/matches", response_model=list[MatchOut])
def list_matches(
    code: str,
    team_id: int | None = None,
    round: int | None = Query(None, ge=1),
    status: MatchStatus | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    upcoming: bool = False,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    league = _get_league(db, code)
    q = select(Match).where(Match.league_id == league.id)
    if team_id is not None:
        q = q.where(or_(Match.home_team_id == team_id, Match.away_team_id == team_id))
    if round is not None:
        q = q.where(Match.round == round)
    if status is not None:
        q = q.where(Match.status == status)
    if date_from:
        q = q.where(Match.kickoff >= datetime.combine(date_from, time.min, timezone.utc))
    if date_to:
        q = q.where(Match.kickoff < datetime.combine(date_to + timedelta(days=1), time.min, timezone.utc))
    if upcoming:
        q = q.where(Match.kickoff > datetime.now(timezone.utc), Match.status == MatchStatus.scheduled)
    q = q.options(
        selectinload(Match.home_team), selectinload(Match.away_team), selectinload(Match.stadium)
    ).order_by(Match.kickoff, Match.id)
    return db.scalars(q.limit(limit).offset(offset)).all()


@router.get("/leagues/{code}/standings", response_model=list[StandingRow])
def standings(code: str, db: Session = Depends(get_db)):
    league = _get_league(db, code)
    teams = db.scalars(select(Team).where(Team.league_id == league.id)).all()
    table = {
        t.id: {"team": TeamBrief.model_validate(t), "played": 0, "won": 0, "drawn": 0, "lost": 0,
               "goals_for": 0, "goals_against": 0}
        for t in teams
    }
    finished = db.scalars(
        select(Match).where(Match.league_id == league.id, Match.status == MatchStatus.finished)
    ).all()
    for m in finished:
        for team_id, gf, ga in ((m.home_team_id, m.home_score, m.away_score),
                                (m.away_team_id, m.away_score, m.home_score)):
            row = table[team_id]
            row["played"] += 1
            row["goals_for"] += gf
            row["goals_against"] += ga
            row["won" if gf > ga else "lost" if gf < ga else "drawn"] += 1
    rows = []
    for row in table.values():
        row["goal_difference"] = row["goals_for"] - row["goals_against"]
        row["points"] = row["won"] * 3 + row["drawn"]
        rows.append(row)
    # K League tiebreakers: points, goals scored, goal difference.
    rows.sort(key=lambda r: (-r["points"], -r["goals_for"], -r["goal_difference"], r["team"].name))
    return [StandingRow(position=i, **r) for i, r in enumerate(rows, start=1)]


@router.get("/matches/{match_id}", response_model=MatchDetail)
def get_match(match_id: int, db: Session = Depends(get_db)):
    match = db.get(Match, match_id)
    if not match:
        raise HTTPException(404, "Match not found")
    return match
