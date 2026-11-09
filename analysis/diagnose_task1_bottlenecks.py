"""Investigate Task 1 service bottlenecks using an existing simulation workbook.

From repository root:
 python analysis/diagnose_task1_bottlenecks.py "run_traceability_2026.11.09_11.00/sim_log_2026.11.09_11.00.xlsx"

Read-only: does not change simulation policies or files. Writes a diagnostic Markdown
report and CSV tables into analysis/reports/task1_diagnostics/.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import pandas as pd

STREAMS = ("pooler", "producer")
STOCKS = ("POOL_WASHED", "POOL_UNWASHED", "POOL_BUFFER")


def pretty(value):
    if pd.isna(value):
        return "n/a"
    if isinstance(value, float):
        return f"{value:,.2f}"
    return f"{int(value):,}"


def marktable(df: pd.DataFrame, cols: list[str] | None = None, max_rows: int = 12) -> str:
    if cols:
        df = df[cols]
    if df.empty:
        return "No rows"
    df = df.head(max_rows)
    lines = ["| " + " | ".join(map(str, df.columns)) + " |", "| " + " | ".join(["---"]*len(df.columns)) + " |"]
    for values in df.itertuples(index=False, name=None):
        lines.append("| " + " | ".join(pretty(v) if isinstance(v,(float,int)) else str(v) for v in values) + " |")
    return "\n".join(lines)


def diagnose(workbook: Path, output_dir: Path):
    workbook = workbook.resolve()
    if not workbook.is_file():
        raise FileNotFoundError(workbook)
    with pd.ExcelFile(workbook) as xls:
        mandatory = {"Stock", "Backorders", "OrderAudit", "Orders", "Fulfillment", "Screening"}
        missing = mandatory - set(xls.sheet_names)
        if missing:
            raise ValueError(f"Missing sheets: {sorted(missing)}. Use an instrumented simulation workbook.")
        audit = pd.read_excel(xls, "OrderAudit")
        orders = pd.read_excel(xls, "Orders")
        stock = pd.read_excel(xls, "Stock")
        backorders = pd.read_excel(xls, "Backorders")
        fulfillment = pd.read_excel(xls, "Fulfillment")
        screening = pd.read_excel(xls, "Screening")
    output_dir.mkdir(parents=True, exist_ok=True)
    last_step = int(fulfillment.Step.max())
    if last_step != 365:
        raise ValueError(f"Expected a 365-day run; got {last_step}")

    for name, df, cols in (
        ("OrderAudit",audit,{"Stream", "Crate Type", "Issuer", "Supplier", "Due Step", "Original RTIs", "On Time RTIs", "Late RTIs", "Outstanding RTIs", "Order ID"}),
        ("Stock",stock,{"Step", "Warehouse", "Crate Type", "Quantity"}),
        ("Backorders",backorders,{"Step", "Warehouse", "Crate Type", "Quantity"}),
    ):
        missing_cols = cols-set(df.columns)
        if missing_cols:
            raise ValueError(f"{name}: missing {sorted(missing_cols)}")

    numeric = ["Original RTIs", "On Time RTIs", "Late RTIs", "Outstanding RTIs", "Due Step"]
    for col in numeric:
        audit[col] = pd.to_numeric(audit[col], errors="raise")
    if not (audit["Original RTIs"] == audit["On Time RTIs"] + audit["Late RTIs"] + audit["Outstanding RTIs"]).all():
        raise ValueError("Order-level mass balance failed. Stop and inspect data.")

    # Only orders due within the horizon belong in the service denominator.
    due = audit.loc[audit["Due Step"] <= last_step].copy()
    due["Not on time RTIs"] = due["Late RTIs"] + due["Outstanding RTIs"]
    due["Counterparty"] = due.apply(lambda r: r["Issuer"] if r["Stream"]=="pooler" else r["Supplier"], axis=1)
    grouped_cols = ["Original RTIs", "On Time RTIs", "Late RTIs", "Outstanding RTIs", "Not on time RTIs"]
    by_type = (due.groupby(["Stream", "Crate Type"], dropna=False)[grouped_cols]
               .sum().reset_index().sort_values("Not on time RTIs", ascending=False))
    by_type["On-time %"] = (100*by_type["On Time RTIs"] / by_type["Original RTIs"]).round(2)
    by_counterparty = (due.groupby(["Stream", "Counterparty"], dropna=False)[grouped_cols]
                       .sum().reset_index().sort_values("Not on time RTIs", ascending=False))
    by_counterparty["On-time %"] = (100*by_counterparty["On Time RTIs"] / by_counterparty["Original RTIs"]).round(2)
    by_type.to_csv(output_dir/"service_by_crate_type.csv", index=False)
    by_counterparty.to_csv(output_dir/"service_by_counterparty.csv", index=False)

    wash_text="Needs Wash" in orders.columns and "Order ID" in orders.columns
    wash_lines=[]
    if wash_text:
        wash = orders[["Order ID", "Needs Wash"]].drop_duplicates("Order ID")
        p = due[due["Stream"] == "pooler"].merge(wash, on="Order ID", how="left")
        p["Wash Requirement"] = p["Needs Wash"].apply(
            lambda v: "Washed-only" if str(v).strip().lower() in ("true", "1", "1.0")
            else "Flexible" if str(v).strip().lower() in ("false", "0", "0.0") else "Unknown")
        by_wash = (p.groupby("Wash Requirement")[grouped_cols].sum().reset_index())
        by_wash["On-time %"] = (100*by_wash["On Time RTIs"] / by_wash["Original RTIs"]).round(2)
        by_wash.to_csv(output_dir/"pooler_service_by_washing_requirement.csv",index=False)
        wash_lines = ["## Pooler delivery performance by washing requirement",marktable(by_wash)]

    # Stock is recorded at the end of each step and is aggregated by node + crate type.
    daily = (stock.loc[(stock.Step>0)&stock.Warehouse.isin(STOCKS)]
             .groupby(["Step","Warehouse","Crate Type"], dropna=False)["Quantity"].sum().reset_index())
    stock_summary = daily.groupby(["Warehouse", "Crate Type"])["Quantity"].agg(
        Average="mean", Minimum="min", Maximum="max", Ending="last",
        Days_at_zero=lambda x: int((x==0).sum())
    ).reset_index()
    stock_summary[["Average", "Minimum", "Maximum", "Ending"]] = stock_summary[["Average", "Minimum", "Maximum", "Ending"]].round(1)
    stock_summary.to_csv(output_dir/"pool_stock_by_type.csv",index=False)

    bd = backorders.loc[(backorders.Step>0) & (backorders.Quantity>0)].copy()
    if not bd.empty:
        back_summary = bd.groupby(["Warehouse", "Crate Type"],dropna=False)["Quantity"].agg(
            Days_with_backorders="count", Highest_backorder="max", Total_outstanding_day_RTIs="sum"
        ).reset_index().sort_values("Total_outstanding_day_RTIs", ascending=False)
    else:
        back_summary = pd.DataFrame(columns=["Warehouse", "Crate Type", "Days_with_backorders", "Highest_backorder", "Total_outstanding_day_RTIs"])
    back_summary.to_csv(output_dir/"backorders_by_node_and_type.csv",index=False)

    sf = screening.loc[screening.Step>0].copy()
    backlog_col = "screened_backlog_uls" if "screened_backlog_uls" in sf.columns else None
    screened_total = int(sf.screened_uls.sum() + (sf[backlog_col].sum() if backlog_col else 0))
    screened_backlog = int(sf[backlog_col].sum()) if backlog_col else 0
    if not (sf.arrived_uls == sf.screened_uls + sf.bypassed_uls).all():
        raise ValueError("Screening arrival accounting failed")
    if not (sf.screened_uls + (sf[backlog_col] if backlog_col else 0) <= sf.capacity_uls).all():
        raise ValueError("Screening capacity exceeded")

    report = ["# Team 7 — Task 1 service bottleneck diagnostic", "",
              f"Workbook: `{workbook}`", "",
              "This is descriptive evidence from one stochastic run, **not proof of causality**.",
              "## Screening capacity allocation", "",
              f"- Total screening admissions: **{screened_total:,} ULs**",
              f"- Backlog re-screened: **{screened_backlog:,} ULs** ({100*screened_backlog/screened_total:.1f}% of total screening)" if screened_total else "- No screening admissions",
              f"- Newly arriving ULs bypassed: **{int(sf.bypassed_uls.sum()):,}**", "",
              "## Service by crate type (due orders only)", marktable(by_type), "",
              "## Service by counterparty (due orders only)", marktable(by_counterparty), "",
              *wash_lines,"",
              "## Pooler stock by type (end-of-day balances)",marktable(stock_summary),"",
              "## Recorded backorders by node/type",marktable(back_summary),"",
              "## Diagnostic interpretation guide", "",
              "- If washed-only Pooler orders perform poorly while washed stock for the same crate type frequently reaches zero, investigate recovery capacity and washed stock allocation.",
              "- If flexible orders are also late with unwashed stock depleted, investigate total available inventory and circulation speed.",
              "- If a few crate types account for most overdue quantity, prioritize crate-type-specific stock rules rather than a global screening-utilization target.",
              "- The `Total_outstanding_day_RTIs` measure is a sum of daily backorder balances (RTI-days), not unique missed orders.",
              "- One run and end-of-day stocks cannot establish a causal mechanism; controlled policy ablations and multiple random seeds are needed.", ""]
    out = output_dir/"task1_bottleneck_diagnostic.md"
    out.write_text("\n".join(report), encoding="utf-8")
    print("\nSERVICE BY CRATE TYPE (largest lateness + outstanding first)")
    print(by_type[["Stream","Crate Type","On-time %","Late RTIs","Outstanding RTIs","Not on time RTIs"]].to_string(index=False))
    print("\nPOOLER STOCK BY CRATE TYPE")
    print(stock_summary[["Warehouse","Crate Type","Average","Ending","Days_at_zero"]].to_string(index=False))
    if wash_text:
        print("\nPOOLER SERVICE BY WASHING REQUIREMENT")
        print(by_wash[["Wash Requirement","On-time %","Late RTIs","Outstanding RTIs"]].to_string(index=False))
    print(f"\nDiagnostic report: {out}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workbook", type=Path, help="One 365-day baseline or traceability Excel workbook")
    parser.add_argument("--out", type=Path, default=Path("analysis/reports/task1_diagnostics"))
    args=parser.parse_args()
    diagnose(args.workbook,args.out)


if __name__ == "__main__":
    main()
