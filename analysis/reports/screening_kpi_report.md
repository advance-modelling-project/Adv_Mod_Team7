# Baseline Screening Performance Analysis

**Project:** Advanced Modeling for Operations — Team 7  
**Scenario:** Baseline (365 simulation days)  
**Simulation run:** November 6, 2026

## 1. Objective

Evaluate the performance of the pooler's screening process before implementing RFID-informed decision-making policies.

The existing simulation was extended with measurement counters without intentionally modifying the original operational policies.

## 2. Results

| Performance Indicator | Result |
|---|---:|
| Simulation days | 365 |
| Daily screening capacity | 20 ULs |
| Total arriving unit loads | 12,903 ULs |
| Unit loads admitted to screening | 6,680 ULs |
| Unit loads bypassing screening | 6,223 ULs |
| Completed recovery operations | 6,660 ULs |
| Overall screening capacity utilization | 91.5% |
| Overall screening bypass rate | 48.2% |
| Days at full screening capacity | 334 of 365 |

One unit load contains 200 RTIs.

## 3. Key Findings

**Finding 1 — High screening utilization**

The pooler utilized 91.5% of its total available screening capacity. Screening admissions reached the daily limit on 334 simulation days.

**Finding 2 — High screening bypass rate**

Approximately 48.2% of incoming unit loads bypassed screening. Under the current model, these loads are transferred directly into unwashed inventory.

This suggests that screening prioritization and recovery scheduling are worth investigating as possible operational improvements.

**Finding 3 — Recovery completion and screening admissions differ**

A total of 6,680 ULs entered screening, while 6,660 ULs completed recovery during the simulation.

The difference of 20 ULs is consistent with the model's one-day processing delay. The final processing buffer should be checked to confirm this explanation.

## 4. Validation

The screening analysis passed the following accounting checks:

- Arriving ULs = screened ULs + bypassed ULs.
- Daily screened ULs did not exceed the configured screening capacity.
- All recorded counts were nonnegative.
- The updated simulation completed all 365 days.

These checks support the consistency of the screening measurements but do not constitute full model validation.

## 5. Proposed Research Direction

Investigate whether RFID-informed screening prioritization and recovery scheduling can improve the availability and circulation of reusable crates.

Potential approaches include selecting which arriving unit loads to screen using recorded crate histories and evaluating the recovery of eligible previously bypassed loads.

These are hypotheses requiring simulation experiments, not proven improvements.

## 6. Limitations and Next Steps

The results come from one stochastic simulation run. Multiple independent replications are necessary before drawing general conclusions.

The next development steps are:

1. Implement accurate order-fulfillment KPIs.
2. Measure RTI detention time across nodes.
3. Define feasible RFID-informed decision-making policies.
4. Compare the baseline with traceability scenarios under controlled operating conditions.

**Conclusion:** The baseline screening operation frequently reaches capacity and bypasses a substantial proportion of incoming loads. This provides a measurable motivation to investigate alternative recovery decisions, although the operational benefits of RFID have not yet been demonstrated.