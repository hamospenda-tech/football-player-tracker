# Football Player Finder

Football Player Finder is a web app that helps football fans, fantasy managers and scouts find and compare players from Europe's top five leagues: the Premier League, La Liga, Serie A, the Bundesliga and Ligue 1. You can load a league's top scorers or a team's squad, then filter, sort and search the players to find exactly who you are looking for.

The player data comes from the API-Football API (https://www.api-football.com).

Live app (through the load balancer): http://3.9.175.112

Demo video: add your video link here


## What the app can do

- Choose a league and a season (2022/23, 2023/24 or 2024/25).
- Load the league's top scorers and assist providers, or pick a team to see its whole squad.
- Search the whole league for a player by name.
- Filter players by name, position, nationality, age, goals and appearances.
- Sort players by goals, assists, rating, appearances, minutes, age or name. You can also click a column heading to sort by it.
- Show clear error messages when something goes wrong, for example when a search is too short or the API limit is reached.
- The bottom of the page shows which server answered, so you can see the load balancer at work.


## How to run it on your own computer

You need Python 3.8 or newer, Git, and a free API key from https://www.api-football.com.

1. Clone the repository and go into the folder:

```
git clone https://github.com/hamospenda-tech/football-player-tracker.git
cd football-player-tracker
```

2. Create a virtual environment and install the packages.

On Windows:

```
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

On macOS or Linux:

```
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

3. Make a copy of the file `.env.example` and name it `.env`. Open it and replace `your-api-football-key-here` with your own API key. The `.env` file is ignored by Git, so your key is never uploaded.

4. Start the app:

```
python app.py
```

5. Open http://127.0.0.1:5000 in your browser.


## How it works

The app has a Python (Flask) backend and a simple HTML, CSS and JavaScript frontend.

When you choose a league or a team, the page asks the Flask backend for the players. The backend then asks API-Football for the data using the secret API key, cleans it up, and sends it back to the page. The browser never talks to API-Football directly, so the API key always stays on the server.

Filtering and sorting happen in the browser on the players that are already loaded. This makes them instant and means they do not use up any API requests.

Every answer from the API is saved for 24 hours. If the same data is asked for again, it comes from the saved copy instead of the API. This keeps the app fast and helps it stay within the free plan's limit of 100 requests per day.

The code is split into these files:

- `app.py` is the web server. It checks what the user asked for and handles errors.
- `players.py` chooses which API data to fetch and turns it into simple player records.
- `api_client.py` makes the actual calls to API-Football, saves answers for 24 hours and turns API problems into friendly messages.
- `templates/index.html` is the page layout.
- `static/app.js` loads the players and does the filtering, sorting and drawing of the table.
- `static/style.css` is the styling.


## The API

I used API-Football (version 3) by API-SPORTS. Documentation: https://www.api-football.com/documentation-v3

The free plan allows 100 requests per day, 10 requests per minute, and only the 2022, 2023 and 2024 seasons.

The app uses these parts of the API:

- `/teams` to list the teams in a league.
- `/players/topscorers` and `/players/topassists` for the league's best players.
- `/players` with a team, to get a team's whole squad.
- `/players` with a name, to search for a player.


## Error handling

The app checks what the user typed before asking the API for anything. For example, a player search needs at least 4 letters, and only the leagues and seasons in the dropdowns are accepted.

If something goes wrong, the user sees a short message in a red box instead of a broken page. This covers a search that is too short, a player who cannot be found, too many requests in one minute, the daily limit being used up, and the API being slow or down. When possible, the app shows the last saved data instead of an error.


## Deployment

The app is deployed on two web servers, web-01 and web-02, with a load balancer, lb-01, in front of them. The load balancer sends visitors to the two servers in turn.

On both web-01 and web-02, I did the following:

1. Installed Python and Git:

```
sudo apt update
sudo apt install -y python3-venv python3-pip git
```

2. Downloaded the code and installed the packages:

```
git clone https://github.com/hamospenda-tech/football-player-tracker.git football-player-finder
cd football-player-finder
python3 -m venv venv
venv/bin/pip install -r requirements.txt
```

3. Created the `.env` file with the API key. I typed the key in a hidden prompt, so it was not shown on screen or saved in the command history, and made the file readable only by my user:

```
read -rsp "API key: " KEY && echo "API_FOOTBALL_KEY=$KEY" > .env && unset KEY
chmod 600 .env
```

4. Set up the app to run with gunicorn as a system service called `football`, so it starts automatically and restarts if it crashes. The service file is `/etc/systemd/system/football.service`:

```
[Unit]
Description=Football Player Finder (gunicorn)
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/football-player-finder
ExecStart=/home/ubuntu/football-player-finder/venv/bin/gunicorn --workers 2 --bind 127.0.0.1:5000 --access-logfile - app:app
Restart=always

[Install]
WantedBy=multi-user.target
```

Then I started it:

```
sudo systemctl daemon-reload
sudo systemctl enable --now football
```

5. Changed the Nginx configuration so that Nginx passes visitors on to the app. Inside `/etc/nginx/sites-available/default`, the main part is:

```
location / {
    proxy_pass http://127.0.0.1:5000;
}
```

I kept the `X-Served-By` header from the earlier tasks, which tells you which server answered. Then I checked and reloaded Nginx:

```
sudo nginx -t
sudo systemctl reload nginx
```

On lb-01, HAProxy was already set up from an earlier task. Its backend sends traffic to both web servers in turn (round-robin):

```
backend www-backend
    balance roundrobin
    server 7241-web-01 35.178.250.230:80 check
    server 7241-web-02 35.178.244.80:80 check
```

The only change I made was in the HTTP frontend. It used to redirect every visitor to HTTPS, which does not work when you open the site by its IP address, so I changed it to send visitors straight to the web servers with `default_backend www-backend`. Then I restarted HAProxy.


## Testing the load balancer

I sent six requests to the load balancer and checked which server answered each one:

```
for i in 1 2 3 4 5 6; do curl -sI http://3.9.175.112 | grep -i x-served-by; done
```

The answers alternated between the two servers: web-01, web-02, web-01, web-02, web-01, web-02.

You can also see this in the browser. Open http://3.9.175.112 and refresh the page. The text at the bottom changes between "Served by 7241-web-01" and "Served by 7241-web-02".


## Challenges

The API I first planned to use, API-Football on RapidAPI, had been removed from RapidAPI. I switched to using API-Football directly from its own website.

The free plan only allows 100 requests a day and 10 a minute, and a whole league has far too many players to download. I solved this by loading only what is needed (top players, one team, or one search), saving every answer for 24 hours, and doing all filtering and sorting in the browser.

API-Football refused requests that did not say which program was sending them, so I added a `User-Agent` header to every request.

On my laptop, my antivirus (AVG) checks all secure internet traffic, which made Python reject the connection to the API. I fixed this with the `truststore` package, which lets Python trust the same certificates as Windows.

Some player statistics were impossible, for example Matheus Cunha with 66 games in a 38-game season. I found that when a player moves to a new club after the season, the API counts his season twice. The app now spots numbers that are impossible for one season and halves them back to the real totals, and marks those players with a note.

While testing on Windows, an old copy of the app kept running in the background, so my changes did not seem to work. I learned to check for and stop the old process before restarting.


## Credits

- Player data, photos and club logos: API-Football by API-SPORTS (https://www.api-football.com)
- Python packages: Flask, Requests, python-dotenv, gunicorn and truststore
- Servers: Nginx and HAProxy
