# Source records

Fields marked `<fill>` are completed from `data/raw/<snapshot_id>/manifest.json` after `collect`.

Snapshot id used for the analysis: `<fill: YYYY-MM-DD>` (set in `src/psg_fatigue/config.py` → `SNAPSHOT_ID`).

---

## Source 1 — Wikipedia: Paris Saint-Germain FC season pages

| Field | Value |
|---|---|
| Owner | Wikimedia Foundation; content by Wikipedia contributors |
| URL | `https://en.wikipedia.org/wiki/2025%E2%80%9326_Paris_Saint-Germain_FC_season` (and 2022–23 → 2026–27 equivalents) |
| Access method | **Automated collection via the MediaWiki Action API** (`action=parse&prop=wikitext|revid&format=json&formatversion=2`), descriptive User-Agent, ≤ 1 request/s |
| Why this method | The API returns the page source (wikitext) with a revision id: structured match templates are parsed reliably, the exact version is citable and re-fetchable (`oldid`), and it respects Wikimedia's access policy. HTML scraping of score websites was rejected (anti-bot protection, terms of use). |
| Pagination | Not required: `action=parse` returns one full page per request (5 requests in total). |
| Extraction date | `<fill: UTC timestamp per page>` |
| Revision ids | 2022–23 `<fill>` · 2023–24 `<fill>` · 2024–25 `<fill>` · 2025–26 `<fill>` · 2026–27 `<fill>` |
| Reuse conditions | Text licensed CC BY-SA 4.0 — attribution required; derived tables credit Wikipedia contributors. |
| Filters applied | Official competitions only (Ligue 1, Coupe de France, Trophée des Champions, UEFA Champions League, UEFA Super Cup, FIFA Club World Cup, FIFA Intercontinental Cup); friendlies excluded; 2022–23 used only for the last official match date before 5 July 2023. |
| Expected coverage | All official PSG matches 2023–24 → 2026–27 (played up to extraction + scheduled fixtures). Reference 2025–26 "Overall record": 56 matches (L1 34, CdF 2, TdC 1, UCL 17, Super Cup 1, Intercontinental 1). |
| How we checked we got the intended data | Page title and revid in manifest; per season × competition, parsed match counts reconciled with the page's own "Overall record" table (`reports/quality/wikipedia_counts.csv`); Ligue 1 = 34 per complete season; Ligue 1 scores cross-checked against Source 2. |
| Known caveats | User-edited content; Club World Cup 2025 dates are US local dates; postponed matches appear out of matchday order. |

## Source 2 — football-data.co.uk: French Ligue 1 results and odds

| Field | Value |
|---|---|
| Owner | Football-Data.co.uk (independent publisher of historical results and betting odds) |
| URL | `https://www.football-data.co.uk/mmz4281/{2324,2425,2526,2627}/F1.csv` (index page: `https://www.football-data.co.uk/francem.php`) |
| Access method | **Downloaded public CSV files**; download and import automated by `collect` / `build` (manual download into the snapshot folder accepted if automated download is blocked — import remains automated). |
| Extraction date | `<fill per file>` |
| File hashes | `<fill sha256 per file>` |
| Reuse conditions | Free download of historical data published for analysis; data credited to Football-Data.co.uk. `<fill: quote the exact terms shown on the site at extraction>` |
| Filters applied | Seasons 2023–24 → 2026–27; analysis rows filtered to matches involving PSG (`Paris SG`) after verifying the label. |
| Expected coverage | 306 matches per complete season (18 teams); 2026–27 partial up to the last round published at extraction. 34 PSG matches per complete season. |
| Odds used | Market-average closing odds `AvgCH/AvgCD/AvgCA` (reference); `B365C*` (sensitivity); fallback `PSC*` then pre-closing `Avg*` (flagged in `odds_source`). Column availability per season recorded in the quality report. |
| How we checked we got the intended data | HTTP 200 + sha256 in manifest; `Div == "F1"` for all rows; row counts per season; date range per season inside the official Ligue 1 calendar; PSG label present and distinct from `Paris FC`. |
| Known caveats | Odds are an international market aggregate, not French operators; "closing" timing defined by the publisher; kick-off `Time` is UK time (not used for joins). |

## Relationship between the sources

| Input | One row = | Join key | Expected relationship |
|---|---|---|---|
| Wikipedia calendar (Ligue 1 subset) | one PSG Ligue 1 match | `(match_date, opponent_canonical)` | 1:1 with football-data PSG rows |
| football-data PSG subset | one PSG Ligue 1 match | `(match_date, opponent_canonical)` | 1:1 |
| Wikipedia calendar (all competitions) | one PSG official match | — | used to compute load features before the join (many-to-one aggregation into each league match) |

Units: goals (count), odds (decimal), probabilities (0–1), rest (calendar days, Europe/Paris dates).
