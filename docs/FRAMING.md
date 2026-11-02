# Framing — Define the decision

## User
A **football trader at a sports betting operator** who sets and adjusts 1X2 (win/draw/loss) odds for Paris Saint-Germain's Ligue 1 matches.

## Decision supported
Whether to apply a **"fatigue adjustment"** to PSG's win probability after congested periods (Champions League midweek, cup matches, short summer break), instead of following the market consensus.

## Main question
**Under Luis Enrique, does fixture congestion reduce PSG's Ligue 1 results beyond what closing odds already anticipate?**

Operationally, for every match we compute the residual
`residual = psg_win − p_win_implied` (actual outcome minus margin-free implied probability)
and compare it between high-load and normal-load matches.

## Sub-questions (→ the three findings)
1. **Performance** — Does load reduce PSG's Ligue 1 performance (win rate, points per match, shots-on-target difference)?
2. **Pricing** — Do closing odds move with load (implied win probability by rest bucket)?
3. **Residual** — Is there a gap the market did not price, in particular at the start of 2025/26 after the 2025 FIFA Club World Cup (≈1 month summer break vs ≈3 months in 2024)?

## Operational definitions
| Concept | Definition |
|---|---|
| Official match | Ligue 1, Coupe de France, Trophée des Champions, UEFA Champions League, UEFA Super Cup, FIFA Club World Cup, FIFA Intercontinental Cup. Friendlies excluded. |
| Rest days | Calendar days (Europe/Paris date) between a Ligue 1 match and PSG's previous official match in any competition. |
| High load (primary) | Rest days ≤ 3 (reference: Champions League Wednesday → Ligue 1 Saturday). |
| Sensitivity thresholds | Rest days ≤ 4; ≥ 4 official matches in the previous 14 days. |
| Reference odds | Market-average closing odds (`AvgCH/AvgCD/AvgCA`); Bet365 closing (`B365C*`) as sensitivity. Fallback order documented in SPEC. |
| Margin removal | Proportional normalisation: `p_i = (1/o_i) / Σ_j (1/o_j)`. |
| Summer break | Days between the last official match of a season and the first official match of the next season (season-level variable). |
| Season-start window | PSG's first 8 Ligue 1 matches of a season (by date). |

## Population
All **official Ligue 1 matches played by PSG** under Luis Enrique — one row = one match from PSG's perspective (≈ 34 × 3 complete seasons + 2026/27 matches already played ≈ 110 rows). Matches in other official competitions are used **only** to measure workload, not as analysis rows.

## Geography
French Ligue 1, home and away. Load-generating matches may be played abroad (Champions League, Club World Cup in the USA). Odds come from the international bookmaker market aggregated by football-data.co.uk, used as the market consensus (not French ANJ-licensed operators specifically).

## Time period
From Luis Enrique's appointment (**5 July 2023**) to the extraction date (**November 2026**): seasons 2023/24, 2024/25, 2025/26 complete and 2026/27 up to the last match played before extraction. The 2022/23 season page is collected **only** to date PSG's last official match before the period (context for the first rest-day / summer-break values); its matches are not analysis rows.

## Decision rule (stated before looking at results)
Recommend a fatigue adjustment **only if** the mean residual in high-load matches is **negative and its 90 % bootstrap confidence interval excludes zero**. Otherwise, the conclusion is: *"the data does not support an adjustment"*. With ≈110 matches and a minority of high-load matches, this is the most likely outcome, and the brief explicitly accepts a well-supported conclusion that the data cannot resolve the question.
