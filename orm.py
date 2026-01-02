from sqlalchemy import Column, Integer, String, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from database import Base

class Match(Base):
    __tablename__ = "matches"

    id = Column(Integer, primary_key=True, index=True)
    match_id = Column(String, unique=True, index=True)
    duration_seconds = Column(Integer)
    killer_win = Column(Boolean)

    players = relationship("MatchPlayer", back_populates="match")


class MatchPlayer(Base):
    __tablename__ = "match_players"

    id = Column(Integer, primary_key=True, index=True)
    match_id = Column(Integer, ForeignKey("matches.id"))
    player_id = Column(String)
    role = Column(String)

    match = relationship("Match", back_populates="players")