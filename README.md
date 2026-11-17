# CheckMetroTime

> A tiny watcher that checks my Porto metro departure times every day and emails me
> the moment the schedule changes. Pure Python standard library, runs free on GitHub Actions.

![Python](https://img.shields.io/badge/Python-3776AB?logo=python&logoColor=white)
![GitHub Actions](https://img.shields.io/badge/GitHub_Actions-2088FF?logo=githubactions&logoColor=white)

## Why

Metro do Porto occasionally adjusts timetables. Instead of checking the site by
hand, this script reads the official **GTFS** feed, works out my departure times
for my stop and direction within a morning window, and only emails me when those
times are different from the last run. No change → no email.

## How it works

1. Downloads the Metro do Porto **GTFS** zip (auto-discovered from the schedules
   page, or a fixed URL you provide).
2. Parses `stops`, `routes`, `trips`, `stop_times`, `calendar` and
   `calendar_dates` to compute the active services for the next weekday.
3. Filters to my stop + headsign (+ optional line) inside a time window.
4. Compares the result to `state.json` from the previous run.
5. If the times changed, sends an email and updates `state.json`.

Runs on a schedule via **GitHub Actions**, which also commits the updated
`state.json` back to the repo. Depends only on the Python standard library.

## Configuration

All configuration is via environment variables (set as **GitHub Actions
Secrets**, or exported locally).

**Required**

| Variable        | Description |
|-----------------|-------------|
| `METRO_STOP`    | Stop name exactly as it appears in the GTFS (e.g. `Fórum Maia`) |
| `METRO_HEADSIGN`| Destination / direction (e.g. `Campanhã`, `Póvoa de Varzim`) |
| `SMTP_USER`     | SMTP username (sender) |
| `SMTP_PASS`     | SMTP password / app password |
| `MAIL_TO`       | Recipient address |

**Optional**

| Variable                            | Default | Description |
|-------------------------------------|---------|-------------|
| `METRO_LINE`                        | all     | Line number (e.g. `A`, `B`, `C`) |
| `METRO_WINDOW_START` / `_END`       | `07:45` / `08:45` | Time window to watch |
| `METRO_GTFS_URL`                    | auto    | Force a GTFS zip URL |
| `METRO_PAGE_URL`                    | metrodoporto.pt page | Page to discover the GTFS link |
| `SMTP_HOST` / `SMTP_PORT`           | `smtp.gmail.com` / `587` | SMTP server |
| `MAIL_FROM`                         | `SMTP_USER` | From address |

## Run locally

```bash
export METRO_STOP="Fórum Maia"
export METRO_HEADSIGN="Campanhã"
export SMTP_USER="you@gmail.com"
export SMTP_PASS="your-app-password"
export MAIL_TO="you@gmail.com"

python3 check_metro.py
```

Without SMTP credentials set, the script prints the email it *would* send instead
of sending it — handy for testing.

## Files

```
CheckMetroTime/
├── .github/workflows/   # scheduled GitHub Actions run
├── check_metro.py       # the watcher
└── state.json           # last known times (auto-updated)
```

## License

Personal project by [Nuno Silva](https://github.com/NunoSilva24). All rights reserved.
