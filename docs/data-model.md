# Data Model

## players
This represents individual players and their long-term progression across matches.
- id (uuid)
- total_xp (int)

## matches
Match outcomes are stored here and used for balance analysis.
- id (uuid)
- duration_seconds (int)
- killer_win (bool)
- created_at (timestamp)

## match_players
Players are linked to matches with role-specific participation and loadout choices.
- match_id (uuid)
- role (enum: killer, survivor)
- perks_used (array[string])

## unlocks
Player-owned unlocks such as perks and cosmetics are stored here, as well as DLC-gated content.
- player_id (uuid)
- unlock_id (string)
- unlock_type (enum: perk, cosmetic)