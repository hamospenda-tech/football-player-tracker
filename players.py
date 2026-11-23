""""Fetches players and teams from API-Football and turns them into simple, flat records.

API-Football's answers are big and deeply nested (player -> statistics -> games -> ...).
This file picks out only what the page needs and returns a flat dictionary per player,
so the frontend never has to understand the API's format.
"""
from api_client import call_api

MAX_TEAM_PAGES = 5  # a squad is usually 2-3 pages of 20 players; this caps API usage

# League matches each team plays in a season (20 teams = 38 games, 18 teams = 34 games)
LEAGUE_MATCHES = {39: 38, 140: 38, 135: 38, 78: 34, 61: 34}
DOUBLED_FIELDS = ("appearances", "minutes", "goals", "assists", "yellow_cards", "red_cards")


def _max_matches(league_id, season):
    """The most league games one player could possibly play in this league and season."""
    if league_id == 61 and season <= 2022:
        return 38  # Ligue 1 had 20 teams until the 2022/23 season
    return LEAGUE_MATCHES.get(league_id, 38)


def _fix_double_counting(record, league_id, season):
    """Undo an API-Football data error for players who changed club after the season.

    The API copies such a player's whole season onto their new club as well, and its
    top-scorer and top-assist lists then add both copies together, so every number is
    exactly doubled (e.g. 66 appearances in a 38-game league). When the numbers are
    impossible for one season, halve them back to the real values.
    """
    max_matches = _max_matches(league_id, season)
    # Impossible = more games than the league has, or more minutes than 90 x every game
    if record["appearances"] > max_matches or record["minutes"] > max_matches * 90:
        for field in DOUBLED_FIELDS:
            record[field] = round(record[field] / 2)
        record["corrected"] = True  # the page shows a "Joined after this season" note
    return record


def _stats_for_league(statistics, league_id):
    """A player can have stats for several competitions; pick the one for this league."""
    for stats in statistics:
        if (stats.get("league") or {}).get("id") == league_id:
            return stats
    return statistics[0] if statistics else {}


def _to_float(value):
    """Turn the API's rating text (e.g. "7.633333") into a number rounded to 2 decimals."""
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return None  # no rating (player barely played): the table shows "–"


def normalize(item, league_id, season):
    """Turn one API-Football player entry into a flat dictionary for the frontend.

    The "or 0" / "or 'Unknown'" parts give safe defaults, because the API often sends
    null for players who did not play much. Without them, sorting and filtering would break.
    """
    player = item.get("player") or {}
    stats = _stats_for_league(item.get("statistics") or [], league_id)
    games = stats.get("games") or {}
    goals = stats.get("goals") or {}
    cards = stats.get("cards") or {}
    team = stats.get("team") or {}
    full_name = f"{player.get('firstname') or ''} {player.get('lastname') or ''}".strip()
    record = {
        "id": player.get("id"),
        "name": player.get("name") or full_name or "Unknown",
        "fullname": full_name,
        "age": player.get("age"),
        "nationality": player.get("nationality") or "Unknown",
        "photo": player.get("photo"),
        "team": team.get("name") or "",
        "team_logo": team.get("logo"),
        "position": games.get("position") or "Unknown",
        "appearances": games.get("appearences") or 0,  # the API spells it "appearences"
        "minutes": games.get("minutes") or 0,
        "goals": goals.get("total") or 0,
        "assists": goals.get("assists") or 0,
        "rating": _to_float(games.get("rating")),
        "yellow_cards": cards.get("yellow") or 0,
        "red_cards": cards.get("red") or 0,
        "corrected": False,
    }
    return _fix_double_counting(record, league_id, season)


# ---------- the three ways to get players ----------
# The free plan only allows 100 requests a day (and 10 a minute), and a whole league
# is about 57 pages of players. So instead of downloading everything, each option
# below uses as few requests as possible.

def get_teams(league, season):
    """All teams in a league and season, sorted by name (1 API request)."""
    data = call_api("/teams", {"league": league, "season": season})
    teams = [
        {"id": entry["team"]["id"], "name": entry["team"]["name"], "logo": entry["team"].get("logo")}
        for entry in data.get("response") or []
        if entry.get("team")
    ]
    return sorted(teams, key=lambda team: team["name"])


def get_top_players(league, season):
    """The league's top scorers and top assist providers combined (2 API requests)."""
    players = {}
    for path in ("/players/topscorers", "/players/topassists"):
        data = call_api(path, {"league": league, "season": season})
        for item in data.get("response") or []:
            record = normalize(item, league, season)
            # Stored by player id, so someone in BOTH lists (e.g. Salah) appears only once
            players[record["id"]] = record
    return list(players.values())


def get_team_players(team, league, season):
    """Every player in one team's squad, with their stats for this league and season.

    The API returns 20 players per "page", so we keep asking for the next page until
    we have them all (usually 2-3 requests), but never more than MAX_TEAM_PAGES.
    """
    players = {}
    page = 1
    while True:
        data = call_api("/players", {"team": team, "league": league, "season": season, "page": page})
        for item in data.get("response") or []:
            record = normalize(item, league, season)
            players[record["id"]] = record
        total_pages = (data.get("paging") or {}).get("total") or 1
        if page >= total_pages or page >= MAX_TEAM_PAGES:
            break
        page += 1
    return list(players.values())


def search_players(name, league, season):
    """Search the whole league for players whose name matches (1 API request)."""
    data = call_api("/players", {"search": name, "league": league, "season": season})
    return [normalize(item, league, season) for item in data.get("response") or []]
