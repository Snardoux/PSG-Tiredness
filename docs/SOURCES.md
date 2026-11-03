# Source records

All values below come from `data/raw/2026-11-02/manifest.json` (written by `uv run psg-fatigue collect`)
and from the generated reports cited in each row.

Snapshot id used for the analysis: **`2026-11-02`** (set in `src/psg_fatigue/config.py` → `SNAPSHOT_ID`).
Collection: 9 requests on 2 November 2026 between 20:00:45 and 20:00:56 UTC, at most one request per
second, User-Agent `psg-fatigue-student-project/0.1 (Albert School M1 data project; contact: snardoux@albertschool.com)`.

---

## Source 1 — Wikipedia: Paris Saint-Germain FC season pages

| Field | Value |
|---|---|
| Owner | Wikimedia Foundation; content by Wikipedia contributors |
| URL | `https://en.wikipedia.org/wiki/2025%E2%80%9326_Paris_Saint-Germain_FC_season` (and the 2022–23 → 2026–27 equivalents; titles use an en dash) |
| Access method | **Automated collection via the MediaWiki Action API** (`action=parse&prop=wikitext|revid&format=json&formatversion=2&redirects=1`), descriptive User-Agent, ≤ 1 request/s, retries with backoff on HTTP 429/5xx (`src/psg_fatigue/collect/wikipedia.py`) |
| Why this method | The API returns the page source (wikitext) with a revision id: the structured match templates (`Football box collapsible`) are parsed reliably, the exact version is citable and re-fetchable (`oldid=<revid>`), and the method follows Wikimedia's access policy. HTML scraping of score websites was rejected (anti-bot protection, terms of use). |
| Pagination | Not required: `action=parse` returns one full page per request (5 requests in total). |
| Missing pages | The API answers HTTP 200 with an `error` object (`missingtitle`) for a missing page; the collector checks the body and fails loudly (tested with a real error response). |
| Extraction date (UTC) | 2022–23 `2026-11-02T20:00:45Z` · 2023–24 `20:00:47Z` · 2024–25 `20:00:48Z` · 2025–26 `20:00:50Z` · 2026–27 `20:00:51Z` |
| Revision ids | 2022–23 `1376880063` · 2023–24 `1382074983` · 2024–25 `1381451747` · 2025–26 `1381451969` · 2026–27 `1383293947` |
| File hashes (sha256) | `wiki_2022-23.json` `c5a1e409f265188999e5771027fae6238014d18b517e3adaabdf66ed60693bf8` · `wiki_2023-24.json` `d45bfb3f302a28362c7deedcec88e8a5f3fa330bd6e3a8367b78b1a542748a67` · `wiki_2024-25.json` `73ca459ca6243960d5487cf4815082658de5f5def2ba4654bb98bb6c387d0c9b` · `wiki_2025-26.json` `bf9418bcb6955b7b805bcebdf72b6bf1102255e55501da1533e492c0b4d84993` · `wiki_2026-27.json` `b663a0c05a84939234527caf0d6c5ffe8581b9c7b25b19b19b426bf856615246` |
| Reuse conditions | Text licensed CC BY-SA 4.0 — attribution required; derived tables credit Wikipedia contributors. |
| Filters applied | Official competitions only (Ligue 1, Coupe de France, Trophée des Champions, UEFA Champions League, UEFA Super Cup, FIFA Club World Cup, FIFA Intercontinental Cup); **16 friendlies excluded** (7 on the 2022–23 page, 9 in the Luis Enrique era); 2022–23 used only for the last official match before 5 July 2023 (3 June 2023). |
| Coverage obtained | 270 official fixtures parsed, 238 played: 50 on the 2022–23 context page and **188 in the Luis Enrique era** (2023–24: 53, 2024–25: 65, 2025–26: 56, 2026–27: 14 played up to 30 October 2026) plus 32 scheduled 2026–27 fixtures. The 2025 Club World Cup (7 matches) is on the 2024–25 page. |
| How we checked we got the intended data | Page title and revid in the manifest; per season × competition, played matches reconciled with each page's own "Overall record" table (`Fb overview2`, played = W + D + L): **30 of 30 rows match** (`reports/quality/wikipedia_counts.csv`); Ligue 1 = 34 per complete season; 2025–26 = 56; Ligue 1 scores, venue and result cross-checked against Source 2 with 0 disagreements (`reports/quality/integration_report.md`). |
| Known caveats | User-edited content; Club World Cup 2025 dates are US local dates; 6 postponed Ligue 1 matches appear out of matchday order; the "Overall record" table has no explicit "Pld" column (we use W + D + L). |

## Source 2 — football-data.co.uk: French Ligue 1 results and odds

| Field | Value |
|---|---|
| Owner | Football-Data.co.uk (independent publisher of historical results and betting odds) |
| URL | `https://www.football-data.co.uk/mmz4281/{2324,2425,2526,2627}/F1.csv` (index page: `https://www.football-data.co.uk/francem.php`). The server redirects to `https://football-data.co.uk/…`; the manifest records the final URL. |
| Access method | **Downloaded public CSV files**; download and import automated by `collect` / `build` (`src/psg_fatigue/collect/footballdata.py`, `src/psg_fatigue/parse/fd_matches.py`). The automated download worked (HTTP 200 for all 4 files): the manual fallback (`collect --register-manual`) was not needed. |
| Extraction date (UTC) | `fd_F1_2324.csv` `2026-11-02T20:00:52Z` · `fd_F1_2425.csv` `20:00:53Z` · `fd_F1_2526.csv` `20:00:55Z` · `fd_F1_2627.csv` `20:00:56Z` |
| File hashes (sha256) | `fd_F1_2324.csv` `ca0a4bf51d5b1ccfd0e1558ea41de6bb829df6c96c759888a87248d296d5adb7` · `fd_F1_2425.csv` `fe6ae6a0c30d05f0ac88e0fc4a31452c7203e2b444703dfa941e22f38f20ab63` · `fd_F1_2526.csv` `898b7ddcd373cfe955ae353b1a98cf7f1c8757ca10b69d53039f4e098e88f192` · `fd_F1_2627.csv` `4e39575f8ce0273a8d53cde3d238ded2094e108504205b7ec584e77db5bdbee8` |
| Reuse conditions | No explicit licence is published on the site. Terms shown on 2 November 2026: home page — *"Simply download for free the available files"* and *"My data is free"*; `https://www.football-data.co.uk/disclaimer.php` — *"Football-Data cannot guarantee the correctness of information contained within, or of information obtained from third parties linked to the Football-Data website."* Data used for non-commercial academic analysis and credited to Football-Data.co.uk. |
| Filters applied | Seasons 2023–24 → 2026–27; analysis rows = matches involving `Paris SG` (label verified in every file and distinct from `Paris FC`, present since 2025–26). |
| Coverage obtained | 2023–24 **306/306**, 2024–25 **306/306**, 2025–26 **306/306**, 2026–27 **80** rows (partial, 21 Aug → 1 Nov 2026); PSG: 34 + 34 + 34 + 9 = **111** matches (`reports/quality/fd_counts.csv`). |
| Odds used | Market-average closing odds `AvgCH/AvgCD/AvgCA` (reference, complete for 998/998 rows); `B365C*` (sensitivity, complete); fallback `PSC*` then pre-closing `Avg*` (recorded in `odds_source`, used for 0 rows). `PSC*` is missing for 153/306 rows in 2025–26 and absent from the 2026–27 file (`reports/quality/fd_columns.csv`). |
| How we checked we got the intended data | HTTP 200 + sha256 in the manifest, re-verified offline at every `build`; content starts with the `Div,` header (an HTML error page would be rejected); `Div == "F1"` for all rows; row counts per season; 18 clubs per season; PSG label present and distinct from `Paris FC`; 0 duplicates on (Date, HomeTeam, AwayTeam) (`reports/quality/quality_report.md`). |
| Known caveats | Odds are an international market aggregate, not French operators; "closing" timing defined by the publisher; kick-off `Time` is UK time (not used for joins); three of the four files start with a UTF-8 byte-order mark (handled by the reader). |

## Relationship between the sources

| Input | One row = | Join key | Expected relationship | Observed |
|---|---|---|---|---|
| Wikipedia calendar (Ligue 1 subset, played, Luis Enrique era) | one PSG Ligue 1 match | `(match_date, opponent_canonical)` | 1:1 with football-data PSG rows | 111 rows, 111 matched |
| football-data PSG subset | one PSG Ligue 1 match | `(match_date, opponent_canonical)` | 1:1 | 111 rows, 111 matched on the exact date (match rate 100 %) |
| Wikipedia calendar (all competitions) | one PSG official match | — | used to compute load features before the join (many-to-one aggregation into each league match) | 188 played matches in the era |

Team names are translated with the reviewed table `config/team_names.csv` (24 clubs; only
`Saint-Étienne` ↔ `St Etienne` and `Paris Saint-Germain` ↔ `Paris SG` differ between sources).

Units: goals (count), odds (decimal), probabilities (0–1), rest (calendar days, dates as published).
