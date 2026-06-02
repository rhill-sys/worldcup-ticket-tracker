# World Cup 2026 Ticket Price Tracker

Tracks the cheapest available ticket listings for every match at **MetLife Stadium**
(New York/New Jersey) and **Hard Rock Stadium** (Miami) during the 2026 FIFA World Cup.

A scheduled GitHub Action runs once a day, queries each ticket source, records the
prices into a CSV, and publishes a dashboard via GitHub Pages — no server, no cost,
no maintenance.

![architecture](https://img.shields.io/badge/runs%20on-GitHub%20Actions-blue) ![cost](https://img.shields.io/badge/cost-%240-brightgreen)

---

## What you get

- **A dashboard** (`docs/index.html`) with a current-price table for all 15 matches
  and a price-history line chart per match. Filter by venue.
- **A daily job** (`.github/workflows/track.yml`) that fetches prices and commits the
  data back to the repo.
- **A price log** (`docs/data/history.csv`) that grows over time so you can see trends.
- **Sources:** SeatGeek, StubHub, and a direct link to FIFA's official resale.

---

## How prices are sourced (read this — it's the important part)

| Source | How it works | What you need |
|---|---|---|
| **SeatGeek** | Public API returns the lowest listing price + listing count per event. **This is the workhorse and the most reliable.** | A free SeatGeek API client ID (2-min signup). |
| **StubHub** | Uses StubHub's catalog/inventory API if you have a partner token. | A StubHub API token (requires approval; optional). |
| **FIFA official resale** | FIFA's resale marketplace has **no public price API** and blocks scraping. The tracker records a **direct link** to the FIFA resale page so you can check it manually. | Nothing. |

Without any keys, the tool still runs and produces the dashboard with FIFA links and
"check listing" links — but to get actual **numbers and history**, add at least the
SeatGeek key. Strongly recommended.

> Prices shown are the lowest listing at fetch time and **exclude fees** (resale fees
> run ~15%). This is an unofficial tracker — confirm on the source before buying.

---

## Setup (about 10 minutes, no coding required)

### 1. Create the repo
1. Create a new repository on GitHub (e.g. `worldcup-ticket-tracker`).
2. Upload all of these files (drag the folder contents into GitHub's "Add file → Upload files").

### 2. Get a free SeatGeek API key (recommended)
1. Go to **https://seatgeek.com/account/develop** and sign up / log in.
2. Create an app — you'll get a **Client ID**.
3. In your GitHub repo: **Settings → Secrets and variables → Actions → New repository secret**.
4. Name it `SEATGEEK_CLIENT_ID`, paste the Client ID, save.

(Optional) If you have a StubHub API token, add a second secret named `STUBHUB_API_TOKEN`.

### 3. Turn on the dashboard (GitHub Pages)
1. **Settings → Pages**.
2. Under "Build and deployment", set **Source = Deploy from a branch**.
3. Branch = `main`, folder = **`/docs`**. Save.
4. After a minute your dashboard is live at
   `https://<your-username>.github.io/<repo-name>/`.

### 4. Run it the first time
1. Go to the **Actions** tab → **Track ticket prices** → **Run workflow**.
2. It fetches prices and commits `docs/data/history.csv` + `docs/data/latest.json`.
3. Refresh the dashboard — data appears. From now on it updates automatically every day.

---

## Customizing

- **Change which matches are tracked:** edit `config.json`. Each match has an `id`,
  `venue`, `date`, `round`, `label`, and a `query` used to find it on the ticket sites.
- **Change the schedule:** edit the `cron` line in `.github/workflows/track.yml`
  (it's in UTC).
- **Turn a source off:** set its `enabled` to `false` in `config.json`.

---

## Run it locally (optional)

```bash
# nothing to install — standard library only
SEATGEEK_CLIENT_ID=your_id python tracker.py
```

This writes to `docs/data/`. Open `docs/index.html` in a browser (or run
`python -m http.server` inside `docs/`) to view the dashboard.

---

## Notes & limitations

- SeatGeek is the reliable numeric source. StubHub's API needs partner access, and
  FIFA exposes no price API, so coverage depends on which keys you add.
- Knockout matches (Round of 32/16, etc.) don't have known team names yet, so those
  are matched by venue + date. After the bracket fills in, update the `label`/`query`
  fields in `config.json` for sharper matching.
- The tracker is fault-tolerant: if a source fails on a given day, that cell is left
  blank and the run still succeeds, so your history stays intact.
