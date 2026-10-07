# Golden fixture formula derivation

The golden expectations were recalculated from the fixture's raw wellness,
sleep, and activity observations using the formula definitions and v1 weights
in the scientific metric documentation and migration seed. No feature-engine
or score-function output was used as an expected-value source.

Recovery uses the arithmetic mean of the prior 28 observed local-day values
for HRV and resting heart rate, when at least seven observations exist. Its
normalized inputs are `clamp(0.5 + HRV deviation% / 50)`,
`clamp(1 - resting-HR deviation / 10)`, Apex sleep architecture divided by
100, and `clamp(1 - prior-day strain / 100)`. The v1 weights are
0.35/0.25/0.25/0.15 and unavailable inputs are omitted before renormalizing.
The sleep architecture input is independently calculated from each fixture
night as the weighted mean of REM `(REM% - 10) / 15`, deep sleep
`(deep% - 10) / 13`, and sleep efficiency; those components use weights
0.40/0.35/0.25 and clamp to 0..1.

Readiness uses recovery/100, sleep architecture/100, and the documented ACWR
transform, weighted 0.45/0.25/0.30 after omitting unavailable components.
The April 1 local cutoff switches only the recovery weights to the fixture's
v2 values. For the v2 assertions, the derivation uses 0.90/0.05/0.03/0.02
against the same normalized inputs. March 16 remains under v1.

The load-spike calculation uses ACWR's normalized spike component and the
prior 28 zero-filled daily loads' population mean and standard deviation.
The distribution component is absent until seven prior active days exist;
the ACWR component then receives all remaining weight. The fixture's prior
active-day counts first reach seven on March 31, from eligible activity dates
March 10, 12, 15, 20, 21, 25, and 30. Before that point an ACWR of 4.0 yields
100 rather than 70, while an ACWR below 1.3 yields zero. March 8 and 9 have
neither an ACWR nor seven prior active days, so their composite is unavailable.

Activity load was independently summed from the recorded HR samples using
sample durations, the athlete's age-derived HRmax (184 bpm), and Edwards zone
points. This gives the seven-date warm-up above. No load is inferred for the
March 17 strength activity because it has no eligible HR source. Strain is
therefore unavailable on March 8 and 9 (no earlier eligible load evidence)
and March 17 (a session exists, but no eligible load observation does). The
prior-day-strain input is unavailable on March 8, 9, 10, and 18. The sparse
baseline rule affects load-spike values through March 30; March 31 onward has
enough prior active days and retains both components.

Aerobic decoupling is recomputed as the first-half minus second-half
normalized-power-to-HR ratio, divided by the first-half ratio. Constant
power/HR sessions on March 12, March 25, and April 8 therefore have 0%
decoupling. On March 15, power is constant while HR falls from 150 to 140 bpm,
so the EF rises in the second half and decoupling is
`100 * (1 - 150/140) = -7.142857%`. The March 20 session remains unavailable:
its highly variable power fails the steady-state gate.

The fixture keeps its original raw observations and all non-affected
expectations. These values are hand-derived regression expectations, not
snapshots captured from a running application.

The two days before the first eligible session also have unavailable acute and
chronic load, rather than an invented zero load history. Their recorded wellness
still permits a daily row and an available sleep-based heuristic estimate.
