""""Football Player Finder: a Flask web app to find, filter and compare football players.

Data comes from API-Football (https://www.api-football.com). The API key is read from
the .env file on the server and is never sent to the browser.

How the app fits together:
    Browser (templates/index.html + static/app.js)
        |  asks our own backend for data, e.g. GET /api/players?league=39&season=2024
        v
    app.py      <- this file: the web server. Checks the request, then calls players.py
        v
    players.py  <- decides WHICH API-Football endpoints to call and cleans up the answers
        v
    api_client.py <- does the actual HTTP call with the secret key, caching and error handling
"""
import logging
import os
import socket

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request
from werkzeug.exceptions import HTTPException

import players
from api_client import ApiError

# Load the secret API key from the .env file (which is git-ignored, so it never
# reaches GitHub) into the environment variable API_FOOTBALL_KEY.
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

app = Flask(__name__)

# The server's hostname (e.g. "7241-web-01"). It is printed in the page footer so that,
# behind the load balancer, you can see which web server answered each request.
SERVER_NAME = socket.gethostname()

# The leagues users can choose from. The ids are API-Football's own league ids.
LEAGUES = [
    {"id": 39, "name": "Premier League", "country": "England"},
    {"id": 140, "name": "La Liga", "country": "Spain"},
    {"id": 135, "name": "Serie A", "country": "Italy"},
    {"id": 78, "name": "Bundesliga", "country": "Germany"},
    {"id": 61, "name": "Ligue 1", "country": "France"},
]
LEAGUE_IDS = {league["id"] for league in LEAGUES}
SEASONS = [2024, 2023, 2022]  # the seasons the API's free plan allows


# ---------- input validation ----------
# Never trust what the browser sends: anyone can type a URL by hand. These helpers
# reject bad input with a clear message (HTTP 400) before we spend an API request on it.

def _int_param(name):
    """Read a whole-number parameter from the URL, e.g. ?league=39."""
    raw = request.args.get(name, "").strip()
    if not raw.isdigit():
        raise ApiError(f"Missing or invalid '{name}' parameter.", 400)
    return int(raw)


def _league_and_season():
    """Read and check the league and season. Only values from our own lists are allowed."""
    league = _int_param("league")
    season = _int_param("season")
    if league not in LEAGUE_IDS:
        raise ApiError("Unknown league. Please choose one from the list.", 400)
    if season not in SEASONS:
        raise ApiError("Only the 2022, 2023 and 2024 seasons are available.", 400)
    return league, season


# ---------- routes (the URLs our server answers) ----------

@app.route("/")
def index():
    """The web page itself. The league and season dropdowns are filled in from the lists above."""
    return render_template("index.html", leagues=LEAGUES, seasons=SEASONS, server=SERVER_NAME)


@app.route("/health")
def health():
    """A tiny check that the server is up, and which server it is (handy for load balancer tests)."""
    return jsonify(status="ok", server=SERVER_NAME)


@app.route("/api/teams")
def api_teams():
    """All teams in a league and season, used to fill the "Team" dropdown."""
    league, season = _league_and_season()
    return jsonify(players.get_teams(league, season))


@app.route("/api/players")
def api_players():
    """Players to show in the table.

    With ?team=...: that team's whole squad.
    Without it:     the league's top scorers and assist providers.
    """
    league, season = _league_and_season()
    if request.args.get("team"):
        team = _int_param("team")
        return jsonify(players.get_team_players(team, league, season))
    return jsonify(players.get_top_players(league, season))


@app.route("/api/search")
def api_search():
    """Search the WHOLE league for a player by name (not just the players already on screen)."""
    league, season = _league_and_season()
    name = request.args.get("name", "").strip()
    # The API needs at least 4 characters; we also only allow characters found in names.
    if len(name) < 4 or not all(char.isalpha() or char in " -'." for char in name):
        raise ApiError("Type at least 4 letters of a player's name (letters only).", 400)
    return jsonify(players.search_players(name, league, season))


# ---------- error handling ----------
# Whatever goes wrong, the browser always gets a short JSON message like
# {"error": "..."} instead of a crash page, and app.js shows it in a red box.

@app.errorhandler(ApiError)
def handle_api_error(error):
    """Errors we expected (bad input, API down, request limit reached)."""
    return jsonify(error=error.message), error.status


@app.errorhandler(Exception)
def handle_unexpected_error(error):
    """Anything we did NOT expect: log the details for us, show a polite message to the user."""
    if isinstance(error, HTTPException):
        return error  # normal web errors such as 404 Not Found pass through unchanged
    logging.exception("Unexpected error")
    return jsonify(error="Something went wrong on the server. Please try again."), 500


# Runs only with "python app.py" on your laptop. On the servers, gunicorn starts the app instead.
if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
