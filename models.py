from pydantic import BaseModel
from typing import List
from enum import Enum

class Role(str, Enum):
    killer = "killer"
    survivor = "survivor"

class MatchPlayer(BaseModel):
    player_id: str
    role: Role
    perks_used: List[str]

class Match(BaseModel):
    match_id: str
    duration_seconds: int
    killer_win: bool
    players: List[MatchPlayer]