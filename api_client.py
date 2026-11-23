""""Talks to the API-Football v3 API, with on-disk caching and friendly error handling.

Every successful API answer is saved in the cache/ folder for 24 hours, so repeated
requests are instant and do not use up the free plan's 100 requests per day. If the
API is down or the daily limit is reached, an older cached copy is used when one exists.
"""
import hashlib
import json
import os
import time

try:
    # Use the operating system's trusted certificates (needed on PCs where antivirus
    # software such as AVG inspects HTTPS traffic). Optional: skipped if not installed.
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass

import requests

BASE_URL = "https://v3.football.api-sports.io"
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")
CACHE_TTL = 24 * 60 * 60  # keep cached answers for 24 hours (in seconds)
TIMEOUT = 15  # seconds to wait for the API before giving up
PLACEHOLDER_KEY = "your-api-football-key-here"


class ApiError(Exception):
    """An error with a message that is safe to show to the user."""

    def __init__(self, message, status=502):
        super().__init__(message)
        self.message = message
        self.status = status


def _cache_file(path, params):
    """Build a unique cache file name for this endpoint and its parameters."""
    key = path + "?" + "&".join(f"{name}={params[name]}" for name in sorted(params))
    return os.path.join(CACHE_DIR, hashlib.sha1(key.encode("utf-8")).hexdigest() + ".json")


def _read_cache(file, max_age):
    """Return the cached data, or None if it is missing or older than max_age seconds."""
    try:
        if max_age is not None and time.time() - os.path.getmtime(file) > max_age:
            return None
        with open(file, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return None


def _write_cache(file, data):
    """Save an API answer to the cache folder."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    temp_file = file + ".tmp"
    with open(temp_file, "w", encoding="utf-8") as handle:
        json.dump(data, handle)
    os.replace(temp_file, file)  # replace in one step so a half-written file is never read


def _stale_or_raise(file, error):
    """Fall back to an expired cached copy if we have one; otherwise report the error."""
    stale = _read_cache(file, None)
    if stale is not None:
        return stale
    raise error


def call_api(path, params):
    """GET an API-Football endpoint and return its JSON, using the cache when possible."""
    # Step 1: if we already asked this exact question in the last 24 hours, answer from
    # the cache. This costs no API request and is instant.
    file = _cache_file(path, params)
    cached = _read_cache(file, CACHE_TTL)
    if cached is not None:
        return cached

    # Step 2: read the secret key from the environment (loaded from .env by app.py).
    # It is only ever sent to API-Football, never to the browser.
    key = os.environ.get("API_FOOTBALL_KEY", "").strip()
    if not key or key == PLACEHOLDER_KEY:
        raise ApiError("The server has no API key configured. Add API_FOOTBALL_KEY to the .env file.", 500)

    # Step 3: call the API. The key goes in a header; the User-Agent is needed because
    # API-Football drops connections that do not send one.
    # Every failure below becomes an ApiError with a friendly message, and if we have an
    # older (expired) cached copy, that is shown instead of an error.
    headers = {"x-apisports-key": key, "User-Agent": "football-player-finder/1.0"}
    try:
        response = requests.get(BASE_URL + path, params=params, headers=headers, timeout=TIMEOUT)
    except requests.exceptions.Timeout:
        return _stale_or_raise(file, ApiError("The football API took too long to respond. Please try again.", 504))
    except requests.exceptions.RequestException:
        return _stale_or_raise(file, ApiError("Could not reach the football API. Please try again later.", 502))

    # Step 4: check the answer. HTTP 429 means "too many requests" (free plan: 10 per minute).
    if response.status_code == 429:
        return _stale_or_raise(file, ApiError(
            "Too many requests in the last minute (the free plan allows 10 per minute). "
            "Please wait a minute and try again.", 429))
    if response.status_code != 200:
        return _stale_or_raise(
            file, ApiError(f"The football API returned an error (HTTP {response.status_code}).", 502))

    try:
        data = response.json()
    except ValueError:
        return _stale_or_raise(file, ApiError("The football API sent an invalid response.", 502))

    # API-Football reports problems (bad key, daily limit, plan limits) in an "errors" field
    errors = data.get("errors")
    if errors:
        text = " ".join(str(value) for value in errors.values()) if isinstance(errors, dict) else str(errors)
        lowered = text.lower()
        if "per minute" in lowered or "too many" in lowered:
            error = ApiError("Too many requests in the last minute (the free plan allows 10 per minute). "
                             "Please wait a minute and try again.", 429)
        elif "limit" in lowered or "requests" in lowered:
            error = ApiError("Today's 100 free API requests are used up. Data you already viewed still "
                             "works; new searches will work again tomorrow.", 429)
        else:
            error = ApiError("Football API: " + text, 502)
        return _stale_or_raise(file, error)

    # Step 5: success. Save it in the cache so the next identical request is free.
    _write_cache(file, data)
    return data
