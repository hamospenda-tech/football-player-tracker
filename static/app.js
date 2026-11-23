// Football Player Finder: loads players from our Flask backend, then filters, searches
// and sorts them in the browser.
"use strict";

// "state" is everything the page remembers: the players currently loaded,
// and which column the table is sorted by (and in which direction).
const state = { players: [], sortKey: "goals", sortDir: "desc" };

// Shortcuts to every element on the page we need, looked up once by their id.
const $ = (id) => document.getElementById(id);
const els = {
  league: $("league"), season: $("season"), team: $("team"),
  name: $("name-filter"), apiSearch: $("api-search"),
  position: $("position"), nationality: $("nationality"),
  minAge: $("min-age"), maxAge: $("max-age"), minGoals: $("min-goals"), minApps: $("min-apps"),
  sortKey: $("sort-key"), sortDir: $("sort-dir"), reset: $("reset-filters"),
  status: $("status"), error: $("error"), rows: $("player-rows"),
  count: $("count"), source: $("source-label"),
};

// ---------- talking to the backend ----------

// Calls one of our own /api/... URLs and returns the JSON. If anything goes wrong
// (no internet, server error, API limit), it throws an Error with a readable message
// (the "error" text our Flask backend sends), which the caller shows in the red box.
async function fetchJson(url) {
  let response;
  try {
    response = await fetch(url);
  } catch (err) {
    throw new Error("Could not reach the server. Check your connection and try again.");
  }
  let data = null;
  try {
    data = await response.json();
  } catch (err) {
    // the server did not send JSON; handled below
  }
  if (!response.ok) {
    throw new Error((data && data.error) || `Server error (HTTP ${response.status}).`);
  }
  return data;
}

function leagueSeason() {
  return { league: els.league.value, season: els.season.value };
}

// Shows (or hides, when message is empty) the red error box.
function showError(message) {
  els.error.textContent = message || "";
  els.error.hidden = !message;
}

// Shows a "Loading…" message and disables the dropdowns while we wait,
// so the user cannot fire off lots of API requests at once.
function setLoading(message) {
  els.status.textContent = message || "";
  els.status.hidden = !message;
  [els.league, els.season, els.team, els.apiSearch].forEach((el) => { el.disabled = Boolean(message); });
}

// Fills the "Team" dropdown with every team in the chosen league and season.
async function loadTeams() {
  els.team.length = 1; // keep only the "All" option
  try {
    const teams = await fetchJson(`/api/teams?${new URLSearchParams(leagueSeason())}`);
    teams.forEach((team) => els.team.add(new Option(team.name, team.id)));
  } catch (err) {
    showError(`Could not load teams: ${err.message}`);
  }
}

// Loads the players for the table: a team's squad if a team is chosen,
// otherwise the league's top scorers and assist providers.
async function loadPlayers() {
  showError("");
  const params = leagueSeason();
  const teamName = els.team.value ? els.team.selectedOptions[0].text : "";
  if (els.team.value) params.team = els.team.value;
  setLoading(teamName ? `Loading the ${teamName} squad…` : "Loading the league's top players…");
  try {
    const players = await fetchJson(`/api/players?${new URLSearchParams(params)}`);
    setPlayers(players, teamName ? `${teamName} squad` : "League top scorers & assist providers");
  } catch (err) {
    setPlayers([], "");
    showError(err.message);
  } finally {
    setLoading("");
  }
}

// "Search whole league" button: asks the API for ANY player in the league with that
// name, even one who is not in the table right now.
async function searchLeague() {
  const name = els.name.value.trim();
  if (name.length < 4) {
    showError("Type at least 4 letters of a player's name to search the whole league.");
    els.name.focus();
    return;
  }
  showError("");
  setLoading(`Searching the league for "${name}"…`);
  try {
    const players = await fetchJson(`/api/search?${new URLSearchParams({ ...leagueSeason(), name })}`);
    els.team.value = "";
    setPlayers(players, `Search results for "${name}"`);
    if (players.length === 0) {
      showError(`No player called "${name}" was found in this league and season.`);
    }
  } catch (err) {
    showError(err.message);
  } finally {
    setLoading("");
  }
}

// ---------- filtering and sorting ----------

// Removes duplicates and empty values, then sorts A to Z.
function uniqueSorted(values) {
  return [...new Set(values.filter(Boolean))].sort((a, b) => a.localeCompare(b));
}

function fillSelect(select, values) {
  const previous = select.value;
  select.length = 1; // keep the "All ..." option
  values.forEach((value) => select.add(new Option(value, value)));
  select.value = values.includes(previous) ? previous : "";
}

// Stores a newly loaded list of players. The Position and Nationality dropdowns are
// built from the players we actually have, so they never offer a choice with 0 results.
function setPlayers(players, label) {
  state.players = players;
  els.source.textContent = label;
  fillSelect(els.position, uniqueSorted(players.map((p) => p.position)));
  fillSelect(els.nationality, uniqueSorted(players.map((p) => p.nationality)));
  render();
}

function numberOrNull(input) {
  const value = input.value.trim();
  return value === "" || Number.isNaN(Number(value)) ? null : Number(value);
}

// FILTERING: keeps only the players that pass EVERY filter the user filled in.
// An empty filter box means "no limit", so it lets every player through.
function filteredPlayers() {
  const name = els.name.value.trim().toLowerCase();
  const position = els.position.value;
  const nationality = els.nationality.value;
  const minAge = numberOrNull(els.minAge);
  const maxAge = numberOrNull(els.maxAge);
  const minGoals = numberOrNull(els.minGoals);
  const minApps = numberOrNull(els.minApps);

  return state.players.filter((p) =>
    (!name || p.name.toLowerCase().includes(name) || p.fullname.toLowerCase().includes(name)) &&
    (!position || p.position === position) &&
    (!nationality || p.nationality === nationality) &&
    (minAge === null || (p.age !== null && p.age >= minAge)) &&
    (maxAge === null || (p.age !== null && p.age <= maxAge)) &&
    (minGoals === null || p.goals >= minGoals) &&
    (minApps === null || p.appearances >= minApps));
}

// SORTING: orders the players by the chosen column. Text columns (name, team...)
// sort alphabetically, number columns numerically. Direction 1 = lowest first,
// -1 = highest first. A copy is sorted so the original list stays unchanged.
function sortPlayers(players) {
  const key = state.sortKey;
  const direction = state.sortDir === "asc" ? 1 : -1;
  return [...players].sort((a, b) => {
    const x = a[key];
    const y = b[key];
    if (x === null || x === undefined) return 1; // missing values always go last
    if (y === null || y === undefined) return -1;
    if (typeof x === "string") return x.localeCompare(y) * direction;
    return (x - y) * direction;
  });
}

// ---------- drawing the table ----------
// Table cells are built with textContent (never innerHTML), so even if the API sent
// strange text such as "<script>", it is shown as plain text and can never run as code.

// One plain table cell. Missing values are shown as "–".
function cell(text, className) {
  const td = document.createElement("td");
  td.textContent = text === null || text === undefined ? "–" : String(text);
  if (className) td.className = className;
  return td;
}

// A table cell with a picture (player photo or club logo), a name, and an optional
// small grey line underneath (the player's full name, or the "Joined after" note).
function imageCell(src, mainText, subText, imgClass) {
  const td = document.createElement("td");
  const wrap = document.createElement("div");
  wrap.className = "with-img";
  if (src) {
    const img = document.createElement("img");
    img.src = src;
    img.alt = "";
    img.loading = "lazy";
    img.className = imgClass;
    wrap.append(img);
  }
  const text = document.createElement("div");
  const main = document.createElement("span");
  main.textContent = mainText;
  text.append(main);
  if (subText && subText !== mainText) {
    const sub = document.createElement("small");
    sub.textContent = subText;
    text.append(sub);
  }
  wrap.append(text);
  td.append(wrap);
  return td;
}

// Redraws the whole table: filter first, then sort, then build one row per player.
// This runs on every keystroke in a filter box, which is why filtering feels instant.
function render() {
  const players = sortPlayers(filteredPlayers());
  els.rows.replaceChildren();

  if (players.length === 0) {
    const tr = document.createElement("tr");
    const td = cell(state.players.length ? "No players match your filters. Try loosening them." : "No players loaded.");
    td.colSpan = 11;
    td.className = "empty";
    tr.append(td);
    els.rows.append(tr);
  }

  for (const p of players) {
    const tr = document.createElement("tr");
    if (p.corrected) {
      tr.title = "This player changed club after the season. The football API counted his season twice " +
        "and lists his new club, so the numbers shown have been halved back to the real totals.";
    }
    tr.append(
      imageCell(p.photo, p.name, p.fullname, "photo"),
      imageCell(p.team_logo, p.team, p.corrected ? "Joined after this season ⓘ" : "", "logo"),
      cell(p.position),
      cell(p.age, "num"),
      cell(p.nationality),
      cell(p.appearances, "num"),
      cell(p.minutes, "num"),
      cell(p.goals, "num strong"),
      cell(p.assists, "num"),
      cell(p.rating === null ? null : p.rating.toFixed(2), "num"),
      cell(`${p.yellow_cards} 🟨 ${p.red_cards} 🟥`, "num"),
    );
    els.rows.append(tr);
  }

  // "22 of 59 shown" tells the user how much the filters removed
  els.count.textContent = state.players.length ? `(${players.length} of ${state.players.length} shown)` : "";
  // Highlight the sorted column header and show its ▲ / ▼ arrow (drawn by style.css)
  document.querySelectorAll("th[data-sort]").forEach((th) => {
    th.classList.toggle("sorted", th.dataset.sort === state.sortKey);
    th.dataset.dir = th.dataset.sort === state.sortKey ? state.sortDir : "";
  });
}

// ---------- events (what happens when the user does something) ----------

// A new league or season means new teams AND new players, so reload both.
async function reloadEverything() {
  els.team.value = "";
  await loadTeams();
  await loadPlayers();
}

// These ask the backend (and so possibly the API) for new data:
els.league.addEventListener("change", reloadEverything);
els.season.addEventListener("change", reloadEverything);
els.team.addEventListener("change", loadPlayers);
els.apiSearch.addEventListener("click", searchLeague);
els.name.addEventListener("keydown", (event) => { if (event.key === "Enter") searchLeague(); });

// These only redraw the table from the players we already have (no API requests):
[els.name, els.position, els.nationality, els.minAge, els.maxAge, els.minGoals, els.minApps]
  .forEach((el) => el.addEventListener("input", render));

els.sortKey.addEventListener("change", () => { state.sortKey = els.sortKey.value; render(); });
els.sortDir.addEventListener("change", () => { state.sortDir = els.sortDir.value; render(); });

// Clicking a column header sorts by that column; clicking it again flips the direction.
// Text columns start A to Z, number columns start with the highest.
document.querySelectorAll("th[data-sort]").forEach((th) => {
  th.addEventListener("click", () => {
    const key = th.dataset.sort;
    if (state.sortKey === key) {
      state.sortDir = state.sortDir === "asc" ? "desc" : "asc";
    } else {
      state.sortKey = key;
      state.sortDir = ["name", "team", "position", "nationality"].includes(key) ? "asc" : "desc";
    }
    if ([...els.sortKey.options].some((o) => o.value === key)) els.sortKey.value = key;
    els.sortDir.value = state.sortDir;
    render();
  });
});

// "Reset filters" empties every filter box and shows all loaded players again.
els.reset.addEventListener("click", () => {
  [els.name, els.minAge, els.maxAge, els.minGoals, els.minApps].forEach((el) => { el.value = ""; });
  els.position.value = "";
  els.nationality.value = "";
  showError("");
  render();
});

// When the page first opens: load the default league's teams and top players.
reloadEverything();
