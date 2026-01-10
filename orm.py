from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, ARRAY, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from database import Base

class Match(Base):
    __tablename__ = "matches"

    id = Column(Integer, primary_key=True, index=True)
    match_id = Column(String, unique=True, index=True)
    duration_seconds = Column(Integer)
    killer_win = Column(Boolean)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)

    players = relationship("MatchPlayer", back_populates="match")


class MatchPlayer(Base):
    __tablename__ = "match_players"

    id = Column(Integer, primary_key=True, index=True)
    match_id = Column(Integer, ForeignKey("matches.id"))
    player_id = Column(String)
    role = Column(String)
    perks_used = Column(ARRAY(String))

    match = relationship("Match", back_populates="players")