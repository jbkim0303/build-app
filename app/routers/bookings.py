import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..deps import get_current_user
from ..models import Booking, BookingStatus, MatchStatus, SeatZone, User
from ..schemas import BookingCreate, BookingOut

router = APIRouter(prefix="/api/bookings", tags=["bookings"])


def _new_reference(code: str) -> str:
    return f"{code}-{secrets.token_hex(4).upper()}"


@router.post("", response_model=BookingOut, status_code=status.HTTP_201_CREATED)
def create_booking(body: BookingCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if body.quantity > settings.max_tickets_per_booking:
        raise HTTPException(422, f"Maximum {settings.max_tickets_per_booking} tickets per booking")

    zone = db.get(SeatZone, body.zone_id)
    if not zone:
        raise HTTPException(404, "Seat zone not found")
    match = zone.match
    if match.status != MatchStatus.scheduled or match.kickoff <= datetime.now(timezone.utc):
        raise HTTPException(409, "Ticket sales for this match are closed")

    # Atomic reservation: only succeeds if enough seats remain, so concurrent
    # requests can never oversell a zone.
    result = db.execute(
        update(SeatZone)
        .where(SeatZone.id == zone.id, SeatZone.sold + body.quantity <= SeatZone.capacity)
        .values(sold=SeatZone.sold + body.quantity)
    )
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(409, "Not enough seats available in this zone")

    booking = Booking(
        reference=_new_reference(match.league.code),
        user_id=user.id,
        zone_id=zone.id,
        quantity=body.quantity,
        unit_price=zone.price,
        total_price=zone.price * body.quantity,
    )
    db.add(booking)
    db.commit()
    db.refresh(zone)
    return booking


@router.get("", response_model=list[BookingOut])
def my_bookings(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.scalars(
        select(Booking).where(Booking.user_id == user.id).order_by(Booking.created_at.desc(), Booking.id.desc())
    ).all()


def _own_booking(db: Session, reference: str, user: User) -> Booking:
    booking = db.scalar(select(Booking).where(Booking.reference == reference.upper()))
    if not booking or (booking.user_id != user.id and not user.is_admin):
        raise HTTPException(404, "Booking not found")
    return booking


@router.get("/{reference}", response_model=BookingOut)
def get_booking(reference: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _own_booking(db, reference, user)


@router.post("/{reference}/cancel", response_model=BookingOut)
def cancel_booking(reference: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    booking = _own_booking(db, reference, user)
    if booking.status == BookingStatus.cancelled:
        raise HTTPException(409, "Booking is already cancelled")
    cutoff = booking.match.kickoff - timedelta(hours=settings.cancel_cutoff_hours)
    if datetime.now(timezone.utc) > cutoff and booking.match.status == MatchStatus.scheduled:
        raise HTTPException(409, f"Bookings can only be cancelled up to {settings.cancel_cutoff_hours}h before kickoff")
    if booking.match.status == MatchStatus.finished:
        raise HTTPException(409, "Match already played")

    db.execute(
        update(SeatZone).where(SeatZone.id == booking.zone_id).values(sold=SeatZone.sold - booking.quantity)
    )
    booking.status = BookingStatus.cancelled
    booking.cancelled_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(booking.zone)
    return booking
