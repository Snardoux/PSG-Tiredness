# Findings, answer and limitations

> Drafted from the generated outputs in `reports/eda/` by the pipeline author, validated by Sacha
> Nardoux. Every number cites the file it comes from. Population: 111 PSG Ligue 1 matches under
> Luis Enrique (12 Aug 2023 – 30 Oct 2026); high load = ≤ 3 rest days (28 matches), normal load =
> ≥ 4 rest days (83 matches). Intervals are 90 % percentile bootstrap CIs (10 000 resamples, seed 42).

## Finding 1 — Performance under load
After ≤ 3 rest days, PSG did not perform worse in Ligue 1 in this sample:

| Primary bucket | n | Win rate | Points per match | Shots-on-target difference |
|---|---|---|---|---|
| High (≤ 3 days) | 28 | 75.0 % [60.7 ; 89.3] | 2.43 [2.11 ; 2.71] | +3.46 [2.18 ; 4.71] |
| Normal (≥ 4 days) | 83 | 68.7 % [60.2 ; 77.1] | 2.27 [2.06 ; 2.47] | +3.36 [2.73 ; 3.95] |

The high-load figures are slightly higher on all three measures, but every interval overlaps the
other bucket's interval widely: the data shows no difference in either direction.
Source: `reports/eda/summary_by_bucket.csv` (definition `primary`), figure `fig3_performance_by_bucket.png`.

## Finding 2 — Does the market price load?
The mean margin-free implied win probability (closing average odds) is **0.666** [0.627 ; 0.702]
for high-load matches and **0.678** [0.658 ; 0.696] for normal-load matches: closing odds rated
PSG's chances 1.2 points lower after short rest, a gap inside both intervals. This comparison does
not control for opponent strength or venue. Over all 111 matches the closing odds are well
calibrated: in each of the five implied-probability bins, the mean implied probability lies
inside the 90 % CI of the actual win rate (for example 0.739 implied vs 0.730 actual
[0.595 ; 0.838], n = 37, in the 0.7–0.8 bin).
Sources: `reports/eda/summary_by_bucket.csv` (`implied_win_prob`), `reports/eda/calibration.csv`,
figures `fig4_implied_vs_actual.png` and `fig7_calibration.png`.

## Finding 3 — Residual and the post-Club World Cup start of 2025–26
The mean residual (actual win − implied win probability) is **+0.084** [−0.063 ; +0.224] in
high-load matches and +0.009 [−0.072 ; +0.089] in normal-load matches; the difference high − normal
is +0.075 [−0.093 ; +0.236]. The sign is positive — PSG won slightly more often than the closing
odds implied after short rest — but the interval includes zero. Consistently, a flat 1-unit bet on
a PSG win returned +0.146 per unit in high-load matches, with an interval [−0.096 ; +0.392] that
also includes zero.

Season start (first 8 Ligue 1 matches of each season):

| Season | Summer break | Wins / 8 | Mean implied win prob. | Cumulative residual after 8 |
|---|---|---|---|---|
| 2023–24 | 70 days | 4 | 0.608 | −0.86 |
| 2024–25 | 83 days | 6 | 0.679 | +0.57 |
| **2025–26** | **31 days** | **5** | **0.691** | **−0.53** |
| 2026–27 | 74 days | 5 | 0.692 | −0.54 |

After the shortest summer break (31 days between the Club World Cup final on 13 July 2025 and the
UEFA Super Cup on 13 August 2025), PSG won its first four league matches (cumulative residual
+0.91), then lost at Marseille, drew at Lille and drew at home to Strasbourg in matches 5 to 8. The window
ended at −0.53, close to 2026–27 (−0.54, 74-day break) and above 2023–24 (−0.86, 70-day break):
the 2025–26 start does not stand out from seasons with a longer break. Mean residual of the
2025–26 window: −0.066 [−0.295 ; +0.147] (8 matches).
Sources: `reports/eda/decision.json`, `reports/eda/sensitivity.csv`, `reports/eda/season_start.csv`,
`reports/eda/season_start_summary.csv`, figures `fig5_residual_by_definition.png` and `fig6_season_start.png`.

## Answer (decision rule)
The rule, fixed in `docs/FRAMING.md` before the results were computed, requires a negative
high-load mean residual whose 90 % CI excludes zero. The observed high-load mean residual is
**+0.084, 90 % CI [−0.063 ; +0.224]** (n = 28): it is not negative and its interval contains zero.
**Conclusion: the data does not support an adjustment** — the trader should not apply a fatigue
adjustment to PSG's Ligue 1 win probability on the basis of club rest days, and can keep following
the closing market consensus. Source: `reports/eda/decision.json` (`rule_satisfied: false`).

## Sensitivity
| Definition | High-load n | High-load mean residual [90 % CI] | Rule satisfied |
|---|---|---|---|
| Primary: ≤ 3 rest days, closing average odds | 28 | +0.084 [−0.063 ; +0.224] | no |
| ≤ 4 rest days | 53 | +0.069 [−0.034 ; +0.168] | no |
| ≥ 4 official matches in the previous 14 days | 8 | −0.017 [−0.307 ; +0.249] | no |
| ≤ 3 rest days, Bet365 closing odds | 28 | +0.089 [−0.059 ; +0.229] | no |

The conclusion is the same under every definition. Only the 14-day definition gives a negative
mean, on 8 matches with an interval 0.56 wide. Source: `reports/eda/sensitivity.csv`.

## Principal limitations
The full list is in `QUALITY_NOTE.md` → "What cannot be trusted". The three most important:
1. **Sample size** — 28 high-load matches give a 90 % CI 0.29 wide on the mean residual; a moderate
   effect in either direction cannot be distinguished from noise.
2. **Load ≠ fatigue** — rest days describe the club calendar, not player minutes, rotation,
   travel or international duty, none of which is observed; bucket comparisons do not control for
   opponent strength or venue.
3. **The market already knows a lot** — closing odds include announced line-ups and known
   absences, so the residual only measures what the market missed; PSG's high implied
   probabilities (median 0.69) leave little room for any residual.

## Appendix — Hypotheses for further investigation (not tested)
1. Rotation before Champions League knockout matches matters more than rest after them (`ucl_within_4d_after`).
2. Load effects depend on opponent strength (top-half vs bottom-half opponents).
3. International duty (player-level minutes) explains the 2025–26 start better than club rest days.
4. Away travel distance after European away matches amplifies the effect.
5. Markets adjusted faster in 2025–26 than in 2023–24 (learning effect).

## Next step
Player-level minutes and availability (official match sheets) to move from club calendar load to
actual player load.
