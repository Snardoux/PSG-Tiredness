# Findings, answer and limitations

> Drafted from `reports/eda/` numbers by the pipeline author, validated by Sacha. Every number must come from a generated file (cite it).

## Finding 1 — Performance under load
`<fill: win rate / points per match / SOT difference, high vs normal, with n and CI — source: summary_by_bucket.csv>`

## Finding 2 — Does the market price load?
`<fill: mean implied win probability high vs normal; does it move? — source: summary_by_bucket.csv, figure 4>`

## Finding 3 — Residual and the post-Club World Cup start of 2025–26
`<fill: mean residual by bucket with 90 % CI; season-start window residual per season, 2025–26 vs others, summer break days — source: season_start.csv, figure 6>`

## Answer (decision rule)
`<fill from decision.json: "Recommend / do not recommend a fatigue adjustment", with the high-load mean residual and its 90 % CI>`

## Sensitivity
`<fill: thresholds ≤4 days and ≥4 matches in 14 days; Bet365 closing instead of market average — source: sensitivity.csv>`

## Principal limitations
See `QUALITY_NOTE.md` → "What cannot be trusted" (summarise the 3 most important here).

## Appendix — Hypotheses for further investigation (not tested)
1. Rotation before Champions League knockout matches matters more than rest after them (`ucl_within_4d_after`).
2. Load effects depend on opponent strength (top-half vs bottom-half opponents).
3. International duty (player-level minutes) explains the 2025–26 start better than club rest days.
4. Away travel distance after European away matches amplifies the effect.
5. Markets adjusted faster in 2025–26 than in 2023–24 (learning effect).

## Next step
Player-level minutes and availability (official match sheets) to move from club calendar load to actual player load.
