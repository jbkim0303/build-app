from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_admin_user
from ..models import Booking, BookingStatus, League, Match, MatchStatus, SeatZone, Team
from ..schemas import MatchCreate, MatchDetail, MatchResult
from ..seed import default_zones

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(get_admin_user)])


@router.post("/matches", response_model=MatchDetail, status_code=status.HTTP_201_CREATED)
def create_match(body: MatchCreate, db: Session = Depends(get_db)):
    league = db.get(League, body.league_id)
    if not league:
        raise HTTPException(404, "League not found")
    home, away = db.get(Team, body.home_team_id), db.get(Team, body.away_team_id)
    if not home or not away:
        raise HTTPException(404, "Team not found")
    if home.id == away.id:
        raise HTTPException(422, "A team cannot play itself")
    if home.league_id != body.league_id or away.league_id != body.league_id:
        raise HTTPException(422, "Both teams must belong to the league")

    stadium_id = body.stadium_id or home.home_stadium_id
    match = Match(
        league_id=body.league_id, round=body.round, home_team_id=home.id, away_team_id=away.id,
        stadium_id=stadium_id, kickoff=body.kickoff,
    )
    if body.zones:
        match.zones = [SeatZone(name=z.name, price=z.price, capacity=z.capacity) for z in body.zones]
    else:
        match.zones = default_zones(home.home_stadium.capacity, league.code)
    db.add(match)
    db.commit()
    db.refresh(match)
    return match


@router.post("/matches/{match_id}/result", response_model=MatchDetail)
def record_result(match_id: int, body: MatchResult, db: Session = Depends(get_db)):
    match = db.get(Match, match_id)
    if not match:
        raise HTTPException(404, "Match not found")
    if match.status == MatchStatus.cancelled:
        raise HTTPException(409, "Match was cancelled")
    if match.kickoff > datetime.now(timezone.utc):
        raise HTTPException(409, "Match has not kicked off yet")
    match.home_score, match.away_score = body.home_score, body.away_score
    match.status = MatchStatus.finished
    db.commit()
    return match


@router.post("/matches/{match_id}/cancel", response_model=MatchDetail)
def cancel_match(match_id: int, db: Session = Depends(get_db)):
    """Cancel (postpone) a match and void every confirmed booking for it."""
    match = db.get(Match, match_id)
    if not match:
        raise HTTPException(404, "Match not found")
    if match.status != MatchStatus.scheduled:
        raise HTTPException(409, f"Match is already {match.status.value}")
    now = datetime.now(timezone.utc)
    zone_ids = [z.id for z in match.zones]
    for booking in db.scalars(
        select(Booking).where(Booking.zone_id.in_(zone_ids), Booking.status == BookingStatus.confirmed)
    ):
        booking.status = BookingStatus.cancelled
        booking.cancelled_at = now
    for zone in match.zones:
        zone.sold = 0
    match.status = MatchStatus.cancelled
    db.commit()
    return match
