from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
from database import SessionLocal
from orm import Match as MatchOrm, MatchPlayer as MatchPlayerOrm
from models import Match, MatchPlayer
from typing import List

app = FastAPI(title="Asymmetrical Horror Liveops")

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Health check
@app.get("/")
def health_check():
    return {"status": "ok"}

# Post a match (mock)
@app.post("/match")
def post_match(match: Match, db: Session = Depends(get_db)):
    # This creates a MatchOrm object.
    db_match = MatchOrm(
        match_id = match.match_id,
        duration_seconds = match.duration_seconds,
        killer_win = match.killer_win
    )

    db.add(db_match)
    db.flush()

    # This adds each player.
    for player in match.players:
        db_player = MatchPlayerOrm(
            match_id = db_match.id,
            player_id = player.player_id,
            role = player.role
        )
        db.add(db_player)

    db.commit()
    return {"status": "stored", "match_id": match.match_id}

# Get example metrics
@app.get("/metrics/winrates")
def get_win_rates():
    """
    This provides a simple view of win rates.
    Design question: Are killers winning too often or too rarely?
    """
    return {
        "killer_win_rate": 0.48,
        "survivor_win_rate": 0.52
    }