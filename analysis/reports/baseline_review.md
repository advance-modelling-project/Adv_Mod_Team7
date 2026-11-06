# Team 7 — Baseline review (first 365-day run)

**Status:** Initial exploratory analysis; not yet a validated multi-replication assessment.  
**Input:** `run_2026.11.06_13.42/sim_log_2026.11.06_13.42.xlsx` (local run, November 6, 2026).  
**Model:** `Adv_Mod_Team7` modular baseline; producer and pooler supply-chain simulator.

## 1. Checks and measured values

| Measure | Observation |
|---|---:|
| Completed simulation days | 365 |
| Initial RTIs | 322,800 |
| Initial stock matches configured default | Yes |
| Sum of recorded end-of-day stocks conserved | Yes |
| Producer-to-RDC flow equals RDC-to-store flow each day | Yes |
| RDC-issued ordered demand | 2,556,724 RTIs |
| Producer-to-RDC shipments | 2,543,074 RTIs |
| Total demand minus shipments | 13,650 RTIs (about 0.53% of demand) |
| RDC-to-pool return shipments | 2,554,200 RTIs |
| Mean washed stock at pooler | 118,776.44 RTIs |
| Mean unwashed stock at pooler | 65,203.29 RTIs |
| Reported mean overdue producer backorders | 0 RTIs |
| Reported mean overdue pooler backorders | 0 RTIs |

Source: output `baseline_summary.csv` and the six generated diagnostic plots.

**Limitations of these checks:** Stock conservation is based on exported end-of-day categories, not on an independent agent-level check for duplicates, missing RTIs, or incorrect within-day transitions. Equality of two flow aggregates also does not prove individual order-level on-time fulfillment.

## 2. Interpretation of the six graphs

1. **Pooler washed and unwashed stocks fluctuate strongly and generally in opposite directions.** Average stock of these two groups is approximately 184,000 RTIs. Changes in composition could affect handling efficiency and wash eligibility, but the graph alone does not establish waste or a bottleneck.
2. **The pooler's recovery-processing buffer is often near 4,000 RTIs (20 ULs).** This is consistent with its configured daily screening limit; measure screened/bypassed arrivals and actual daily capacity use to test whether it is a binding constraint.
3. **Reported overdue backorders are zero throughout the entire run, across all four crate types.** This is a statement about the current reporting rule, not proof of a 100% on-time fill rate. Service effects under baseline conditions may have little room for improvement; investigate recovery efficiency, inventory residence, and sensitivity to higher demand/lower capacity.
4. **Return movements from RDC to pool are batched.** Frequent 6,600/13,200-RTI spikes are consistent with 33-UL truckload dispatches, at 200 RTIs per UL. Reverse flows should not be assessed solely by daily smoothness.
5. **Producer 6's stock is consistently lower than the other producers' stocks.** The code assigns producer 6 only one compatible crate type (TYPE_2); other producers have two. A lower total inventory is expected structurally and is not automatically poor performance. Normalize per eligible crate type, producer throughput, or days of supply before comparing producers.
6. **The total demand/shipment gap of 13,650 RTIs needs reconciliation.** RDC orders have 1–3 day lead times. The difference may be entirely explained by orders not yet due on day 365. The supplementary `check_order_gap.py` script tests this using the workbook's creation steps and lead times.

## 3. KPI suitability for the project

| KPI | Current status | Action before scenario comparison |
|---|---|---|
| Total recorded stock / mean inventory | Available | Report by location/crate type and add independent conservation test |
| Daily movement throughput | Available | Report by link and review truck-batch interpretation |
| Outstanding overdue backlog (end of day) | Available | Explain explicitly that this is not a fill rate |
| Screening utilization and bypass rate | Not directly logged | Track incoming ULs, screened ULs, bypassed ULs per day |
| Order-level on-time fill rate | Not directly logged | Track order ID, due date, quantity due and quantity fulfilled by due date |
| RTI detention time | Not directly exported | Aggregate transitions from existing `arrival_step` timestamps |
| Reuse cycles completed per RTI | Not directly exported | Increment cycle counter at a precisely defined loop-completion event |
| Washing / repair operations | Not directly logged | Track counts of washed, repaired, and screened RTIs/ULs |

## 4. Immediate sequence of work

- **First:** Run the order-horizon audit to classify the 13,650-RTI difference.
- **Second:** Review baseline model consistency and separate deterministic code optimizations from changes in baseline policy (notably `random.sample` replaced by slicing).
- **Third:** Add verified order and processing event counters while leaving existing policy behavior unchanged.
- **Fourth:** Use a few reproducible independent replications and decide which KPIs show meaningful operational variation.
- **Then:** Select RFID-informed policies based on diagnosed problems; evaluate their individual and combined effects.

## 5. Dashboard (future phase, not current scope)

Once the model exposes stable, tested KPIs and scenario configuration, develop a team-accessible dashboard for running selected simulations, viewing stored progress, comparing scenarios, and reviewing experiment results. Consider a lightweight Streamlit application first. Avoid building dashboard-specific logic inside the simulation agents.

## 6. Validation boundary

This is one observed stochastic run. No RFID policy has been evaluated yet. No cost savings, service improvements, or causal bottlenecks are established by these charts alone. The next steps are aimed at producing evidence suitable for Tasks 1–3 of the assignment.
