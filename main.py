from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks, Query
from sqlalchemy.orm import Session, aliased
from sqlalchemy import func, and_, column, select, cast, Integer
from database import SessionLocal, Base, engine
from orm import Match as MatchOrm, MatchPlayer as MatchPlayerOrm
from models import Match, MatchPlayer
from typing import List
from redis_client import redis_client
from datetime import datetime, timedelta, timezone
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

# This is used to refresh the analytics cache.
def refresh_analytics_cache(redis):
    keys = [
        "analytics:killer_win_rate",
        "analytics:average_match_duration",
        "analytics:perk_pick_rates",
        "analytics:killer_win_rate:7d",
        "analytics:killer_win_rate:30d"
    ]

    for key in redis.scan_iter("analytics:killer_win_rate:timeseries:*"):
        redis.delete(key)

    for key in redis.scan_iter("analytics:perk_pick_rates:timeseries:*"):
        redis.delete(key)

    for key in keys:
        redis.delete(key)

# Health check
@app.get("/")
def health_check():
    return {"status": "ok"}

# Post a match (mock)
@app.post("/match")
def post_match(match: Match, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    # Validation for number of players
    if len(match.players) != 5:
        raise HTTPException(
            status_code=400,
            detail="A match must contain exactly 5 players."
        )
    
    # Validation for roles
    killers = [p for p in match.players if p.role == "killer"]
    survivors = [p for p in match.players if p.role == "survivor"]

    if len(killers) != 1:
        raise HTTPException(
            status_code=400,
            detail="A match must contain exactly 1 killer."
        )
    
    if len(survivors) != 4:
        raise HTTPException(
            status_code=400,
            detail="A match must contain exactly 4 survivors."
        )
    
    # Validation for unique player IDs
    player_ids = [p.player_id for p in match.players]
    if len(player_ids) != len(set(player_ids)):
        raise HTTPException(
            status_code=400,
            detail="Duplicate player IDs detected."
        )
    
    # Validation for number of perks equipped
    for player in match.players:
        if len(player.perks_used) > 4:
            raise HTTPException(
                status_code=400,
                detail="Players may not equip more than 4 perks."
            )

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

    background_tasks.add_task(refresh_analytics_cache, redis_client)

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
    matches = db.query(MatchOrm).order_by(MatchOrm.timestamp.asc()).all()

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

    cached = redis_client.get("analytics:killer_win_rate")

    if cached:
        return json.loads(cached)
    
    total_matches = db.query(MatchOrm).count()
    killer_wins = db.query(MatchOrm).filter(MatchOrm.killer_win == True).count()

    win_rate = (killer_wins / total_matches) if total_matches > 0 else 0

    response_data = {
        "total_matches": total_matches,
        "killer_wins": killer_wins,
        "killer_win_rate": round(win_rate, 2)
    }

    redis_client.set("analytics:killer_win_rate", json.dumps(response_data))

    return response_data

@app.get("/analytics/killer-win-rate/recent")
def killer_win_rate(days: int = 7, db: Session = Depends(get_db)):
    cache_key = f"analytics:killer_win_rate:{days}d"

    cached = redis_client.get(cache_key)
    
    if cached:
        return json.loads(cached)
    
    since = datetime.now(timezone.utc) - timedelta(days=days)

    total_matches = db.query(MatchOrm).filter(MatchOrm.created_at >= since).count()
    killer_wins = db.query(MatchOrm).filter(MatchOrm.created_at >= since, MatchOrm.killer_win == True).count()

    win_rate = (killer_wins / total_matches) if total_matches > 0 else 0

    result = {
        "days": days,
        "total_matches": total_matches,
        "killer_win_rate": round(win_rate, 2)
    }

    redis_client.setex(cache_key, 300, json.dumps(result))

    return result

@app.get("/analytics/killer-win-rate/7d")
def killer_win_rate_7d(db: Session = Depends(get_db)):
    cache_key = "analytics:killer_win_rate:7d"

    cached = redis_client.get(cache_key)

    if cached:
        return json.loads(cached)

    cutoff = datetime.utcnow() - timedelta(days=7)

    total = db.query(MatchOrm).filter(MatchOrm.timestamp >= cutoff).count()

    wins = db.query(MatchOrm).filter(and_(MatchOrm.timestamp >= cutoff, MatchOrm.killer_win == True)).count()

    win_rate = (wins / total) if total > 0 else 0

    result = {
        "window": "7d",
        "total_matches": total,
        "killer_wins": wins,
        "killer_win_rate": round(win_rate, 3)
    }

    redis_client.setex(cache_key, 3600, json.dumps(result))
    return result

@app.get("/analytics/killer-win-rate/30d")
def killer_win_rate_30d(db: Session = Depends(get_db)):
    cache_key = "analytics:killer_win_rate:30d"

    cached = redis_client.get(cache_key)

    if cached:
        return json.loads(cached)

    cutoff = datetime.utcnow() - timedelta(days=30)

    total = db.query(MatchOrm).filter(MatchOrm.timestamp >= cutoff).count()

    wins = db.query(MatchOrm).filter(and_(MatchOrm.timestamp >= cutoff, MatchOrm.killer_win == True)).count()

    win_rate = (wins / total) if total > 0 else 0

    result = {
        "window": "30d",
        "total_matches": total,
        "killer_wins": wins,
        "killer_win_rate": round(win_rate, 3)
    }

    redis_client.setex(cache_key, 3600, json.dumps(result))

    return result

@app.get("/analytics/killer-win-rate/timeseries")
def killer_win_rate_timeseries(days: int = 30, interval: str = Query("day", regex="^(day|hour)$"), db: Session = Depends(get_db)):
    cache_key = f"analytics:killer_win_rate:timeseries:{interval}:{days}d"

    cached = redis_client.get(cache_key)

    if cached:
        return json.loads(cached)
    
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    if interval == "day":
        truncated = func.date_trunc("day", MatchOrm.timestamp).label("bucket")
    else:
        truncated = func.date_trunc("hour", MatchOrm.timestamp).label("bucket")

    subq = (
        select(
            truncated,
            cast(MatchOrm.killer_win, Integer).label("win")
        )
        .where(MatchOrm.timestamp >= cutoff)
    ).subquery()

    query = (
        select(
            subq.c.bucket,
            func.count().label("matches"),
            func.sum(subq.c.win).label("wins"),
        )
        .group_by(subq.c.bucket)
        .order_by(subq.c.bucket)
    )

    results = db.execute(query).all()

    points = []

    for r in results:
        win_rate = (r.wins / r.matches) if r.matches else 0
        points.append({
            "time": r.bucket.isoformat(),
            "matches": r.matches,
            "killer_win_rate": round(win_rate, 3)
        })

    response = {
        "interval": interval,
        "days": days,
        "points": points
    }

    redis_client.setex(cache_key, 300, json.dumps(response))

    return response

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

@app.get("/analytics/perk-pick-rates/timeseries")
def perk_pick_rates_timeseries(days: int = 30, interval: str = Query("day", regex="^(day|hour)$"), db: Session = Depends(get_db)):
    cache_key = f"analytics:perk_pick_rates:timeseries:{interval}:{days}d"

    cached = redis_client.get(cache_key)

    if cached:
        return json.loads(cached)
    
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    match_alias = aliased(MatchOrm)

    if interval == "day":
        truncated = func.date_trunc("day", match_alias.timestamp).label("bucket")
    else:
        truncated = func.date_trunc("hour", match_alias.timestamp).label("bucket")

    subq = (
        select(
            truncated,
            func.unnest(MatchPlayerOrm.perks_used).label("perk")
        )
        .join(match_alias, MatchPlayerOrm.match_id == match_alias.id)
        .where(match_alias.timestamp >= cutoff)
    ).subquery()

    query = (
        select(
            subq.c.bucket,
            subq.c.perk,
            func.count().label("count")
        )
        .group_by(subq.c.bucket, subq.c.perk)
        .order_by(subq.c.bucket)
    )

    results = db.execute(query).all()

    points_dict = {}

    for bucket, perk, count in results:
        bucket_str = bucket.isoformat()
        if bucket_str not in points_dict:
            points_dict[bucket_str] = {}
        points_dict[bucket_str][perk] = count

    points = [
        {"time": time, "perk_usage": usage}
        for time, usage in sorted(points_dict.items())
    ]

    response = {
        "interval": interval,
        "days": days,
        "points": points
    }

    redis_client.setex(cache_key, 300, json.dumps(response))

    return response

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