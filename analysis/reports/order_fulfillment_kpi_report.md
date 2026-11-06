# Team 7 — Baseline Order Fulfillment KPI Report

**Course:** Advanced Modeling for Operations  
**Task:** T07B — Order-level fulfillment measurement  
**Scenario:** Unmodified baseline decision policies, with additional monitoring  
**Run:** `run_2026.11.06_19.13` (365 simulated operating days)  
**Status:** Preliminary single-run findings; statistical replication pending

## Objective

Extend the existing baseline simulation to distinguish the quantity delivered on time, quantity delivered late, outstanding overdue quantity, and quantity not yet due at the end of the simulation. Measure pooler-to-producer and producer-to-RDC orders separately. Pooler orders are entered in unit loads (ULs) and normalized to RTIs (200 RTIs per UL) for consistent comparisons.

## Implementation verification

- All **12 automated tests passed** (eight order-tracking tests and four screening tests).
- The updated model completed all **365 simulated days**.
- The output workbook included order-fulfillment monitoring and an audit containing **3,930 order rows**.
- **Every order balances: PASS**.
- Both fulfillment stream mass-balance checks: **PASS**.

## Results

| Metric | RDC orders fulfilled by producers | Producer orders fulfilled by pooler |
|---|---:|---:|
| Quantity created (RTIs) | 2,546,610 | 2,514,600 |
| Quantity due by simulation horizon (RTIs) | 2,532,849 | 2,508,000 |
| Quantity delivered on time (RTIs) | 2,532,849 | 2,504,400 |
| Quantity delivered late (RTIs) | 0 | 3,600 |
| Outstanding overdue at horizon (RTIs) | 0 | 0 |
| Not yet due at horizon (RTIs) | 13,761 | 6,600 |
| On-time quantity fill rate for orders due by horizon | 100.00% | 99.86% |

### Interpretation

1. The RDC order stream was delivered fully on time in this simulation run.
2. The pooler delivered **3,600 RTIs late**, equivalent to **18 ULs**; the on-time quantity fill rate for orders due by the horizon was **99.86%**.
3. **Zero overdue quantity at the end does not imply zero late deliveries during the run.** The order-level tracking makes this distinction explicit.
4. In the separate previous baseline screening run, admissions used **91.5%** of annual configured capacity and **48.2%** of arriving ULs bypassed screening. These observations motivate studying recovery decisions, but **do not establish a causal connection** to the late deliveries here.

## Limits and follow-up checks

- These are **single-run** outcomes. Demand and other model events are random; seeds and independent replications will be required before estimating expected performance or comparing policy variants.
- The existing audit confirms quantity accounting; further checks should investigate actual delivery times, the specific late orders, crate types, washing requirement, and inventories on the relevant days.
- An on-time **quantity** fill rate is different from an on-time **order-count** rate and does not measure lateness duration.
- To evaluate circularity and traceability, the model still needs validated RTI detention-time and reuse-event measurements.
- Preserve baseline operational decision rules until the traceability scenario is introduced as a separate, controlled policy change.

## Proposed next work

1. Review the late deliveries in the OrderAudit sheet and determine when and why they occurred, without assuming causation.
2. Add measurement-only detention-time KPIs with automated tests.
3. Introduce reproducible seed management and controlled replicated simulations.
4. Use the validated baseline measures to specify RFID-based recovery and inventory policies for Task 1.
