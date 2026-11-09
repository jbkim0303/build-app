import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UTCDateTime(TypeDecorator):
    """Stores datetimes as UTC and always returns timezone-aware values
    (SQLite drops tzinfo otherwise)."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return value.replace(tzinfo=timezone.utc)


class MatchStatus(str, enum.Enum):
    scheduled = "scheduled"
    finished = "finished"
    cancelled = "cancelled"


class BookingStatus(str, enum.Enum):
    confirmed = "confirmed"
    cancelled = "cancelled"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    password_hash: Mapped[str] = mapped_column(String(255))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)

    bookings: Mapped[list["Booking"]] = relationship(back_populates="user")


class League(Base):
    __tablename__ = "leagues"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)  # e.g. "K1"
    name: Mapped[str] = mapped_column(String(100))  # e.g. "K League 1"
    country: Mapped[str] = mapped_column(String(50))
    season: Mapped[int] = mapped_column(Integer)

    teams: Mapped[list["Team"]] = relationship(back_populates="league")
    matches: Mapped[list["Match"]] = relationship(back_populates="league")


class Stadium(Base):
    __tablename__ = "stadiums"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    city: Mapped[str] = mapped_column(String(50))
    capacity: Mapped[int] = mapped_column(Integer)


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(primary_key=True)
    league_id: Mapped[int] = mapped_column(ForeignKey("leagues.id"))
    name: Mapped[str] = mapped_column(String(100), unique=True)
    short_name: Mapped[str] = mapped_column(String(10))
    city: Mapped[str] = mapped_column(String(50))
    home_stadium_id: Mapped[int] = mapped_column(ForeignKey("stadiums.id"))

    league: Mapped[League] = relationship(back_populates="teams")
    home_stadium: Mapped[Stadium] = relationship()


class Match(Base):
    __tablename__ = "matches"

    id: Mapped[int] = mapped_column(primary_key=True)
    league_id: Mapped[int] = mapped_column(ForeignKey("leagues.id"))
    round: Mapped[int] = mapped_column(Integer)
    home_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    away_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    stadium_id: Mapped[int] = mapped_column(ForeignKey("stadiums.id"))
    kickoff: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)
    status: Mapped[MatchStatus] = mapped_column(Enum(MatchStatus), default=MatchStatus.scheduled)
    home_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    away_score: Mapped[int | None] = mapped_column(Integer, nullable=True)

    league: Mapped[League] = relationship(back_populates="matches")
    home_team: Mapped[Team] = relationship(foreign_keys=[home_team_id])
    away_team: Mapped[Team] = relationship(foreign_keys=[away_team_id])
    stadium: Mapped[Stadium] = relationship()
    zones: Mapped[list["SeatZone"]] = relationship(
        back_populates="match", cascade="all, delete-orphan", order_by="SeatZone.price.desc()"
    )

    __table_args__ = (CheckConstraint("home_team_id != away_team_id", name="ck_distinct_teams"),)


class SeatZone(Base):
    """A ticket category for one match (e.g. VIP, Premium, Home Supporters)."""

    __tablename__ = "seat_zones"

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"))
    name: Mapped[str] = mapped_column(String(50))
    price: Mapped[int] = mapped_column(Integer)  # KRW
    capacity: Mapped[int] = mapped_column(Integer)
    sold: Mapped[int] = mapped_column(Integer, default=0)

    match: Mapped[Match] = relationship(back_populates="zones")

    __table_args__ = (
        UniqueConstraint("match_id", "name", name="uq_zone_per_match"),
        CheckConstraint("sold >= 0 AND sold <= capacity", name="ck_sold_range"),
    )

    @property
    def available(self) -> int:
        return self.capacity - self.sold


class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[int] = mapped_column(primary_key=True)
    reference: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    zone_id: Mapped[int] = mapped_column(ForeignKey("seat_zones.id"))
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price: Mapped[int] = mapped_column(Integer)
    total_price: Mapped[int] = mapped_column(Integer)
    status: Mapped[BookingStatus] = mapped_column(Enum(BookingStatus), default=BookingStatus.confirmed)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    cancelled_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)

    user: Mapped[User] = relationship(back_populates="bookings")
    zone: Mapped[SeatZone] = relationship()

    @property
    def match(self) -> Match:
        return self.zone.match
