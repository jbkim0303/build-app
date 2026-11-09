from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .models import BookingStatus, MatchStatus


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- auth ----------
class UserCreate(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        v = v.strip().lower()
        if "@" not in v or v.startswith("@") or v.endswith("@"):
            raise ValueError("invalid email address")
        return v


class UserOut(ORM):
    id: int
    email: str
    name: str
    is_admin: bool


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ---------- league data ----------
class LeagueOut(ORM):
    id: int
    code: str
    name: str
    country: str
    season: int


class StadiumOut(ORM):
    id: int
    name: str
    city: str
    capacity: int


class TeamOut(ORM):
    id: int
    name: str
    short_name: str
    city: str
    home_stadium: StadiumOut


class TeamBrief(ORM):
    id: int
    name: str
    short_name: str


class SeatZoneOut(ORM):
    id: int
    name: str
    price: int
    capacity: int
    available: int


class MatchOut(ORM):
    id: int
    round: int
    kickoff: datetime
    status: MatchStatus
    home_team: TeamBrief
    away_team: TeamBrief
    stadium: StadiumOut
    home_score: int | None
    away_score: int | None


class MatchDetail(MatchOut):
    zones: list[SeatZoneOut]


class StandingRow(BaseModel):
    position: int
    team: TeamBrief
    played: int
    won: int
    drawn: int
    lost: int
    goals_for: int
    goals_against: int
    goal_difference: int
    points: int


# ---------- admin ----------
class SeatZoneCreate(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    price: int = Field(ge=0)
    capacity: int = Field(gt=0)


class MatchCreate(BaseModel):
    league_id: int
    round: int = Field(ge=1)
    home_team_id: int
    away_team_id: int
    stadium_id: int | None = None  # defaults to home team's stadium
    kickoff: datetime
    zones: list[SeatZoneCreate] | None = None  # defaults to standard zones


class MatchResult(BaseModel):
    home_score: int = Field(ge=0)
    away_score: int = Field(ge=0)


# ---------- bookings ----------
class BookingCreate(BaseModel):
    zone_id: int
    quantity: int = Field(ge=1)


class BookingOut(ORM):
    id: int
    reference: str
    quantity: int
    unit_price: int
    total_price: int
    status: BookingStatus
    created_at: datetime
    cancelled_at: datetime | None
    zone: SeatZoneOut
    match: MatchOut
