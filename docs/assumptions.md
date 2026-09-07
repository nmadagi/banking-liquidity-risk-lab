# Assumptions and where they come from

All figures USD millions. The bank is synthetic; the weights are not.

## Regulatory liquidity coverage ratio (US LCR rule, 12 CFR 249)

Outflow rates over 30 days, by deposit category (subpart D):

| category | weight | note |
|---|---|---|
| retail, stable (insured, established relationship) | 3% | |
| retail, less stable (insured, rate sensitive or new) | 10% | |
| small business (insured, treated as retail) | 5% | midpoint of the retail band used for simplicity |
| corporate operational (non financial) | 25% | operational deposits |
| corporate non-operational (non financial) | 40% | |
| financial institution non-operational | 100% | |
| unsecured wholesale maturing inside 30 days | 100% | |

Draws on undrawn commitments: retail and small business credit lines 5%, credit facilities to non-financial corporates 10%, liquidity facilities to non-financial corporates 30%, facilities to financial institutions 40%.

Inflows: 50% of contractual loan payments due inside 30 days; total inflows capped at 75% of total outflows. Contractual payments due inside 30 days are modeled as 4% of commercial loans, 1% of mortgages and 5% of consumer loans, which is a simplification of a full maturity ladder.

HQLA: reserves and treasuries at 100% (level 1); agency MBS at 85% (level 2A); investment grade corporate bonds at 50% (level 2B). Level 2 assets capped at 40% of the total, level 2B at 15%.

## Regulatory net stable funding ratio (US NSFR rule, 12 CFR 249 subpart K)

Available stable funding: capital 100%, funding with residual maturity over one year 100%, stable retail and small business deposits 95%, less stable retail 90%, operational deposits 50%, non-operational deposits from non-financial corporates 50%, funding from financial institutions with maturity under six months 0%.

Required stable funding: reserves 0%, treasuries 5%, agency MBS 15%, level 2B securities 50%, residential mortgages 65%, other loans over one year 85%, other assets 100%, undrawn commitments 5%.

## Internal combined stress scenario (the firm's own)

The internal scenario is deliberately harsher than the regulatory calibration and shaped in time. It is a cash flow projection, not a ratio.

| item | internal | regulatory | why |
|---|---|---|---|
| retail stable | 4% | 3% | modest cushion on the calmest money |
| retail less stable | 13% | 10% | rate sensitive and 2023 showed digital runs are faster |
| small business | 8% | 5% | operating accounts move slowly but the segment includes uninsured balances |
| corporate operational | 22% | 25% | slightly below the rule: the operational link is real, and history in this bank says 12% |
| corporate non-operational | 50% | 40% | history in this bank reached 42% |
| financial institution non-op | 100% | 100% | nothing to soften |
| draws: retail lines | 6% | 5% | |
| draws: corporate credit | 10% | 10% | |
| draws: corporate liquidity | 35% | 30% | liquidity facilities are drawn exactly when the borrower is in trouble |
| draws: financial institution | 45% | 40% | |
| loan inflows | 50% of contractual | 50% capped | same rate, no 75% cap because the projection is daily |
| wholesale rollover | 0% | n/a | no unsecured lender is assumed to roll |
| HQLA haircuts | MBS 20%, corporate bonds 60%, no caps | MBS 15%, corporate 50%, capped | stressed market liquidity |
| time shape | about 70% of the 30 day runoff in the first ten days | flat 30 day bucket | the run is front loaded; the survival horizon depends on the shape more than the total |
| after day 30 | a further 40% of the 30 day amount, spread to day 90 | none | the slow bleed continues |

Survival horizon: the first day cumulative net outflow exceeds counterbalancing capacity (post-haircut HQLA, no discount window, no management actions). If it never does inside 90 days the horizon is reported as beyond 90 (shown as 91).

## The limit framework

| indicator | trigger | limit | direction |
|---|---|---|---|
| LCR | 115% | 110% | floor (regulatory minimum 100%) |
| NSFR | 108% | 105% | floor (regulatory minimum 100%) |
| survival horizon, internal combined | 60 days | 45 days | floor |
| uninsured deposits / deposits | 40% | 45% | cap |
| financial institution deposits / deposits | 6% | 9% | cap |
| loans / deposits | 100% | 110% | cap |
| undrawn commitments / HQLA | 150% | 175% | cap |
| 30 day wholesale maturities / HQLA | 25% | 30% | cap |

Internal limits sit above the regulatory minimum by design: the firm never meets the regulator at the floor.

## Challenge rule

For a proposed assumption change: floor = the stronger of (realized worst 30 day outflow, model reading) times 1.10, rounded up to the whole percent. Proposed below realized history: rejected. Proposed at or above the floor: accepted, with a re-test condition. In between, and the floor is below the current assumption: counter-proposed at the floor. Otherwise rejected.

## The synthetic bank

Opening balance sheet 130,000: deposits 92,000 across six segments, short wholesale 6,000, term funding 18,000, other liabilities 3,000, equity 11,000; assets are reserves 9,000, treasuries 20,000, agency MBS 9,000, corporate bonds 2,000, loans 82,000, other 8,000. Undrawn commitments 40,000 across four facility types.

Two planted stress episodes: a market-wide wobble in October 2023 (stress index peaks at 0.35) and an idiosyncratic confidence event from March 10, 2025 (index at 1.0 for fourteen business days, then decays). Daily outflow per segment is the segment's stress sensitivity times the stress index to the power 1.5, divided by 26, so a full-strength 30 day window realizes about one sensitivity unit. Part of what leaves comes back over the following 126 calm days (70% for insured retail, down to 30% for financial institutions). Stress draws on commitments land in the loan book and repay over 120 calm days.

One business initiative: an institutional cash program in Q2 2026 that brings in 2,500 of financial institution and 1,500 of corporate non-operational deposits, adds 2,000 of commercial loans and 1,000 of new facilities.

Treasury desk behavior: reserves kept between 3,000 and 14,000 by selling or buying treasuries; contingency funding of 6,000 in secured term borrowing once a stress has consumed 28% of the liquid asset pool, repaid only from cash above 9,000.

## Sources

- 12 CFR Part 249, Liquidity Risk Measurement Standards (LCR, subpart D outflow rates; NSFR, subpart K).
- Basel Committee, Basel III: The Liquidity Coverage Ratio and liquidity risk monitoring tools (2013), and Basel III: the net stable funding ratio (2014).
- Federal Reserve, Regulation YY, section 252.35 (liquidity risk management, internal stress testing, limits).
- FDIC and Federal Reserve post-mortems on the March 2023 bank failures, for the speed and front loading of uninsured deposit runs.
