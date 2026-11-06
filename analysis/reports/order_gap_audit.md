# Team 7 - order horizon reconciliation

Source: `run_2026.11.06_13.42\sim_log_2026.11.06_13.42.xlsx`

## Aggregate quantities

| Quantity | RTIs |
|---|---:|
| Total RDC-issued demand | 2,556,724 |
| RDC orders due by day 365 | 2,543,074 |
| RDC orders not yet due by day 365 | 13,650 |
| Producer-to-RDC shipments through day 365 | 2,543,074 |
| Total ordered minus shipped | 13,650 |
| Due orders minus shipped (aggregate only) | 0 |

**Does not-yet-due demand exactly explain the observed gap? True**

## Interpretation

The observed aggregate gap is fully explained by orders whose due dates lie after the simulation horizon.

**Caution:** This is not an on-time fill-rate calculation. The exported Orders sheet records created orders but does not link shipments to order IDs or record actual fulfillment times.

## Orders with due dates after the horizon

| Created on day | Lead time (days) | Due on day | Quantity (RTIs) |
|---:|---:|---:|---:|
| 363 | 3 | 366 | 3,767 |
| 364 | 2 | 366 | 2,938 |
| 364 | 3 | 367 | 693 |
| 365 | 1 | 366 | 808 |
| 365 | 2 | 367 | 3,011 |
| 365 | 3 | 368 | 2,433 |

## What the model must record next

For rigorous KPI measurement, log each order ID, due day, fulfilled quantity, actual dispatch day, and any remaining quantity after due date.
