from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from database import SessionLocal, Base, engine
from orm import Match as MatchOrm, MatchPlayer as MatchPlayerOrm
from models import Match, MatchPlayer
from typing import List
from redis_client import redis_client
import json

# This creates all tables if they don't exist.
Base.metadata.create_all(bind=engine)

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
    # This prevents duplicate match ids.
    existing = db.query(MatchOrm).filter(
        MatchOrm.match_id == match.match_id
    ).first()

    if existing:
        raise HTTPException(
            status_code=400,
            detail="Match already exists."
        )
    
    # This ensures that there are only 5 players in a match.
    if len(match.players) != 5:
        raise HTTPException(
            status_code=400,
            detail="Match must have exactly 5 players"
        )
    
    # This ensures that there is only 1 killer in a match.
    killers = [p for p in match.players if p.role == "killer"]

    if len(killers) != 1:
        raise HTTPException(
            status_code=400,
            detail="Match must have exactly 1 killer."
        )

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
            role = player.role,
            perks_used = player.perks_used
        )
        db.add(db_player)

    db.commit()

    # This invalidates the Redis cache for analytics.
    keys_to_invalidate = [
        "analytics:killer_win_rate",
        "analytics:average_match_duration",
        "analytics:perk_pick_rates"
    ]

    for key in keys_to_invalidate:
        redis_client.delete(key)

    return {"status": "stored", "match_id": match.match_id}

@app.get("/matches/{match_id}")
def get_match(match_id: str, db: Session = Depends(get_db)):
    match = db.query(MatchOrm).filter(MatchOrm.match_id == match_id).first()

    if not match:
        raise HTTPException(status_code=404, detail="Match not found.")
    
    players = db.query(MatchPlayerOrm).filter(
        MatchPlayerOrm.match_id == match.id
    ).all()

    return {
        "match_id": match.match_id,
        "duration_seconds": match.duration_seconds,
        "killer_win": match.killer_win,
        "players": [
            {
                "player_id": p.player_id,
                "role": p.role
            }
            for p in players
        ]
    }

@app.get("/matches")
def get_all_matches(db: Session = Depends(get_db)):
    # This gets all matches.
    matches = db.query(MatchOrm).all()

    results = []
    for match in matches:
        # This gets all players for the match.
        match_data = {
            "match_id": match.match_id,
            "duration_seconds": match.duration_seconds,
            "killer_win": match.killer_win,
            "players": [
                {
                    "player_id": player.player_id,
                    "role": player.role,
                    "perks_used": player.perks_used
                } for player in match.players
            ]
        }
        results.append(match_data)
    
    return results

@app.get("/analytics/killer-win-rate")
def killer_win_rate(db: Session = Depends(get_db)):
    cache_key = "analytics:killer_win_rate"

    cached = redis_client.get(cache_key)
    if cached:
        return json.loads(cached)

    total_matches = db.query(MatchOrm).count()
    killer_wins = db.query(MatchOrm).filter(MatchOrm.killer_win == True).count()

    win_rate = (killer_wins / total_matches) if total_matches > 0 else 0

    result = {
        "total_matches": total_matches,
        "killer_wins": killer_wins,
        "killer_win_rate": round(win_rate, 2)
    }

    redis_client.setex(cache_key, 60, json.dumps(result))

    return result

@app.get("/analytics/average-match-duration")
def average_match_duration(db: Session = Depends(get_db)):
    cache_key = "analytics:average_match_duration"

    cached = redis_client.get(cache_key)
    if cached:
        return json.loads(cached)

    avg_duration = db.query(func.avg(MatchOrm.duration_seconds)).scalar()

    result = {
        "average_match_duration_seconds": round(float(avg_duration), 2) if avg_duration else 0
    }

    redis_client.setex(cache_key, 60, json.dumps(result))

    return result

@app.get("/analytics/perk-pick-rates")
def perk_pick_rates(db: Session = Depends(get_db)):
    cache_key = "analytics:perk_pick_rates"

    cached = redis_client.get(cache_key)
    if cached:
        return json.loads(cached)

    results = (
        db.query(
            func.unnest(MatchPlayerOrm.perks_used).label("perk"),
            func.count().label("count")
        )
        .group_by("perk")
        .all()
    )

    pick_rates = {
        row.perk: row.count
        for row in results
    }

    redis_client.setex(cache_key, 60, json.dumps(pick_rates))

    return pick_rates

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