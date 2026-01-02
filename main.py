from fastapi import FastAPI
from models import Match, MatchPlayer
from typing import List

app = FastAPI(title="Asymmetrical Horror Liveops")

# Health check
@app.get("/")
def health_check():
    return {"status": "ok"}

# Post a match (mock)
@app.post("/match")
def post_match(match: Match):
    return {"received": match}

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