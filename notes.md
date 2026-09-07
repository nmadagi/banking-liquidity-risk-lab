# notes

Build decisions, in the order I made them. Newest at the bottom.

## what this is for

A second line seat looks at a banking book (deposits, loans, undrawn commitments) and has to say three things: what moved and what it did to liquidity, whether the book is inside its limits, and whether a proposed change to a stress assumption is defensible. I wanted one small app that does all three on a book I control, so every number can be traced.

## why synthetic

Real deposit data is confidential and, more to the point, I needed to plant a stress episode and a business initiative and then see whether the metrics catch them. The generator is the only place the "true" behavior lives. Nothing downstream reads its parameters; the metrics, limits and models only see balances, which is the position a second line is actually in.

## the balance sheet has to balance

Reserves are the plug: every deposit that arrives is cash until it is lent, every loan is cash that left. This is what makes the attribution honest. Applying one driver's change and letting reserves absorb it is the same accounting the bank does.

## calibration took most of the day

First cut: deposits shrank all history because the rate gap term was too strong and loans outgrew deposits, so every ratio trended down and the story was noise. Fixed the drifts, cut the rate sensitivity, and added recovery after an episode (customers come back, in proportion to how sticky the segment is).

Second cut: the contingency borrowing triggered on a reserve floor, which the treasury desk never let it hit because it sold bills first. Now it triggers when the liquid asset pool is down 28% in a stress, which is how a contingency funding plan is actually written, and it repays only out of excess cash so the bank does not quietly drain its HQLA repaying it.

Third cut: the survival horizon was binary, either beyond 90 days or under 30, because the internal scenario put everything inside 30 days and had almost no tail. Added a slower tail to day 90. The horizon now moves in the range where the limit lives.

## the LCR paradox is real and I kept it

During the spring 2025 event the LCR barely moved while the bank burned a third of its HQLA. Financial institution deposits carry a 100% weight, so a dollar leaving takes a dollar of HQLA and a dollar of assumed outflow with it: the ratio holds, the cash goes. The survival horizon caught it, the ratio did not. That is the strongest argument in the app for running an internal cash flow test next to the regulatory ratio, so I left it in and wrote it up on the limits tab.

## the growth program is the headline

Deposits grew, loans grew, the balance sheet looked healthier, and LCR fell twelve points through the internal limit. Lending the new money is most of it; the new deposits themselves added almost nothing because they were 100% runoff money. The "held as cash" counterfactual is one line of code and it is the whole argument a second line would make to the business.

## model selection, and what I changed my mind about

I started by ranking the four candidates on out-of-sample error and the ridge regression won by a hair. Then I looked at what it said per segment: an 18% run on insured stable retail, which has never happened in this or any history, because a linear model gives every segment the same stress slope. So the evidence model is now chosen by fidelity: refit on all history, read each segment's worst stress, score the gap to what the segment actually did. Gradient boosting wins on both panels. The out-of-sample table stays in the app because its last two columns are the most important thing on the page: no model saw the 2025 event coming at its onset.

I also tried a "stressed reading" that swept the model over a grid of stress features and trailing outflows. It produced combinations that never co-occur (peak stress with a 99th percentile trailing outflow on the same day) and over-read the stable segments. Replaced with the model's largest prediction on the segment's own stress days. Less clever, more honest.

Dropped the rate gap feature: in this synthetic world it is a constant times the policy rate per segment, so it only identifies the segment and it dominated the importance table for the wrong reason. TODO in src/ml.py.

## the challenge rule is written down on purpose

Floor equals the stronger witness times 1.10, rounded up. Below history: rejected. At or above the floor: accepted with a re-test condition. In between: counter-proposed at the floor. A rule that can be read is a rule that can be argued with, which is the point of a second line.

Floating point caught me: 0.10 * 1.10 * 100 is 11.000000000000002 and math.ceil made it 12. Now rounded before the ceiling. Test added.

## things I would do next

- Maturity ladder for loans and term funding instead of flat 30 day fractions.
- Intraday view for the operational deposits.
- A real stress index built from market data and the bank's own indicators.
- More than one history for the model selection, so the fidelity score is not scored on the same episode it learned from.
