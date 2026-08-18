# Housing Bot — Amsterdam & Utrecht room alerts

Polls Dutch rental portals every ~10 minutes via GitHub Actions, filters for
**rooms under €900 suitable for a male student**, and emails a dense alert with
everything needed to decide, plus a direct apply link. No machine of yours needs
to stay on.

## Sources

| Source | Method | Status |
|---|---|---|
| **Kamernet** | JSON from the page's `__NEXT_DATA__` blob | Primary — ~100 listings/run |
| **DirectWonen** | HTML via BeautifulSoup | Secondary — rooms + studios |
| Pararius | — | **Disabled: returns HTTP 403 to all automated clients** |

Kamernet server-renders its results as JSON, so that parser reads structured
data instead of scraping the DOM and is immune to CSS redesigns. Verified live:
its `searchCategories` and `pageNo` query params work, but `maxRent`, `radius`
and `suitableForGenders` are **silently ignored**, so price, area and gender are
all enforced client-side.

Pararius and its sibling huurwoningen.nl block non-browser clients outright. The
parser is kept as an inert stub so it can be revived if that ever changes.

## Filtering

Two stages, so that detail pages (one HTTP request each) are only fetched for
listings that already look promising:

1. **Cheap** — price ≤ €900, city in the Amsterdam/Utrecht commuter allowlist,
   move-in on or before 31 Oct 2026, not a parking spot/garage/chalet.
2. **Strict** — needs the detail page: tenant gender preference, occupation
   requirements, and Dutch/English keyword scanning of the description.

The guiding rule is **reject only on positive evidence**. Most Dutch listings
state no preference at all; rejecting silence would discard nearly everything.
A listing is dropped only when it explicitly excludes you — e.g. `Gender: Female`,
`alleen meiden`, `geen studenten`, `working professionals only`.

In live testing this removed 5 of 8 candidate rooms as female-only.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env      # then fill in your Gmail + app password
python main.py --dry-run  # safe: collects and filters, sends nothing
```

### Gmail credentials

Requires a **Google App Password** (not your account password), which in turn
requires 2-Step Verification to be enabled on the account:

1. Enable 2FA at <https://myaccount.google.com/security>
2. Create one at <https://myaccount.google.com/apppasswords>
3. Put the 16-character value in `.env` as `SMTP_APP_PASSWORD`

### GitHub Actions

```bash
gh secret set SMTP_EMAIL
gh secret set SMTP_APP_PASSWORD
gh secret set ALERT_RECIPIENT_EMAIL
gh workflow run scraper.yml     # manual test run
```

**Make the repository public.** At ~4,300 runs/month the schedule would blow the
2,000-minute free quota on a private repo; public repos get unlimited Actions
minutes. Secrets stay encrypted either way, and `seen_listings.json` holds no
personal data.

## Flags

| Flag | Effect |
|---|---|
| `--dry-run` | Collect and filter, never send email |
| `--no-store` | Do not write `seen_listings.json` |
| `--limit N` | Enrich at most N listings (fast testing) |

## Deduplication

`data/seen_listings.json` maps `<source>:<listing_id>` to metadata, so IDs from
different sites cannot collide. Writes are atomic (temp file + `os.replace`), a
corrupt file degrades to "start empty" rather than crashing, and entries older
than 120 days are pruned. The workflow commits this file back to the repo after
each run, which is what makes deduplication persist across runs.

The **first run** sends one seeding digest rather than dozens of alerts, and
says so in the email.

## Adding a source

Subclass `BaseParser` in `src/parsers/`, implement `collect()`, optionally
`enrich()`, and add it to `PARSERS` in `main.py`. The base class provides the
session, rotating User-Agents, exponential backoff, and 403 detection (403 is
never retried — a bot wall is not a transient fault). A parser that raises is
logged and skipped; one dead site never kills the run.

## Known limitations

- **GitHub cron is best-effort.** `*/10` commonly drifts to 10–30 minutes under
  load. No free scheduler can do better.
- **Datacenter IPs may be blocked** even where a home connection is not. If
  Kamernet starts returning 403 in Actions logs, that is the failure mode.
- DirectWonen's cards do not expose surface area, so `Size` is often absent
  for that source.
