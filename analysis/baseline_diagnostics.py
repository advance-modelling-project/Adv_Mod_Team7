"""Team 7 baseline diagnostics for the current modular CLSC simulator.

Run from the repository root after running `python main.py`:
    python analysis/baseline_diagnostics.py

Optional:
    python analysis/baseline_diagnostics.py run_YYYY.MM.DD_HH.MM/sim_log_YYYY.MM.DD_HH.MM.xlsx

Produces summary metrics, a daily table, plots and a short findings file in
<run_folder>/baseline_diagnostics/. Does not modify the simulation or its output.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

EXPECTED_INITIAL_RTIS = 322_800  # Professor's default initial configuration


def latest_workbook() -> Path:
    paths = list(Path(".").glob("run_*/sim_log_*.xlsx"))
    if not paths:
        raise FileNotFoundError(
            "No run_*/sim_log_*.xlsx found. First execute `python main.py` "
            "from the project root, or provide the Excel workbook path."
        )
    return max(paths, key=lambda p: p.stat().st_mtime)


def read_sheet(path: Path, name: str, columns: list[str]) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name=name)
    missing = set(columns).difference(df.columns)
    if missing:
        raise ValueError(f"Sheet {name!r} is missing columns: {sorted(missing)}")
    return df


def series_sum(df: pd.DataFrame, steps: pd.Index, mask: pd.Series) -> pd.Series:
    return df.loc[mask].groupby("Step")["Quantity"].sum().reindex(steps, fill_value=0)


def line_chart(data: pd.DataFrame, columns: list[str], title: str,
               ylabel: str, target: Path) -> None:
    ax = data[columns].plot(figsize=(11, 5), linewidth=1.8)
    ax.set(title=title, xlabel="Simulation day", ylabel=ylabel)
    ax.grid(alpha=0.2)
    ax.figure.tight_layout()
    ax.figure.savefig(target, dpi=180)
    plt.close(ax.figure)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workbook", nargs="?", type=Path,
                        help="Workbook to analyze; defaults to latest run_*/sim_log_*.xlsx")
    args = parser.parse_args()
    workbook = args.workbook if args.workbook else latest_workbook()
    if not workbook.is_file():
        raise FileNotFoundError(workbook)
    output = workbook.parent / "baseline_diagnostics"
    output.mkdir(parents=True, exist_ok=True)

    stock = read_sheet(workbook, "Stock", ["Step", "Warehouse", "Crate Type", "Quantity"])
    flows = read_sheet(workbook, "Flows", ["Step", "Origin", "Destination", "Crate Type", "Quantity"])
    backlog = read_sheet(workbook, "Backorders", ["Step", "Warehouse", "Crate Type", "Quantity"])
    orders = read_sheet(workbook, "Orders", ["Step", "Issuer", "Quantity", "UoM"])

    steps = pd.Index(sorted(stock["Step"].unique()), name="Step")
    daily = pd.DataFrame(index=steps)

    for label, warehouse in [
        ("pool_washed", "POOL_WASHED"),
        ("pool_unwashed", "POOL_UNWASHED"),
        ("pool_processing_buffer", "POOL_BUFFER"),
        ("rdc_reverse", "RDC_REVERSE"),
        ("rpos_display", "RPOS_DISPLAY"),
        ("rpos_reverse", "RPOS_REVERSE"),
    ]:
        daily[label] = series_sum(stock, steps, stock["Warehouse"].eq(warehouse))

    daily["producer_stock"] = series_sum(stock, steps, stock["Warehouse"].str.startswith("PRO_"))
    daily["total_reported_stock"] = stock.groupby("Step")["Quantity"].sum().reindex(steps, fill_value=0)
    daily["producer_backorders"] = series_sum(backlog, steps, backlog["Warehouse"].str.startswith("PRO_"))
    daily["pool_backorders"] = series_sum(backlog, steps, backlog["Warehouse"].str.startswith("POOL_"))
    daily["total_backorders"] = daily["producer_backorders"] + daily["pool_backorders"]

    is_producer = flows["Origin"].str.startswith("PRO_")
    for label, mask in [
        ("flow_pool_to_pro", flows["Origin"].eq("POOL") & flows["Destination"].str.startswith("PRO_")),
        ("flow_pro_to_rdc", is_producer & flows["Destination"].eq("RDC")),
        ("flow_rdc_to_rpos", flows["Origin"].eq("RDC") & flows["Destination"].eq("RPOS")),
        ("flow_rpos_to_rdc", flows["Origin"].eq("RPOS") & flows["Destination"].eq("RDC")),
        ("flow_rdc_to_pool", flows["Origin"].eq("RDC") & flows["Destination"].eq("POOL")),
    ]:
        daily[label] = series_sum(flows, steps, mask)

    valid_rdc_orders = orders["Issuer"].eq("RDC_1") & orders["UoM"].eq("RTI")
    daily["demand_ordered"] = orders.loc[valid_rdc_orders].groupby("Step")["Quantity"].sum().reindex(steps, fill_value=0)
    daily.to_csv(output / "baseline_daily.csv")

    active = daily.loc[daily.index > 0]
    if active.empty:
        raise ValueError("No completed simulation steps found (only initial Step 0).")

    initial_stock = int(daily.iloc[0]["total_reported_stock"])
    stock_conserved = bool((daily["total_reported_stock"] == initial_stock).all())
    matches_expected = initial_stock == EXPECTED_INITIAL_RTIS
    rdc_flow_matched = bool((active["flow_pro_to_rdc"] == active["flow_rdc_to_rpos"]).all())

    summary = {
        "workbook": str(workbook),
        "completed_days": len(active),
        "initial_rtis_reported": initial_stock,
        "default_initial_rtis_expected": EXPECTED_INITIAL_RTIS,
        "initial_stock_matches_default": matches_expected,
        "end_of_day_stock_conserved": stock_conserved,
        "pro_to_rdc_equals_rdc_to_rpos_each_day": rdc_flow_matched,
        "total_demand_ordered_rtis": int(active["demand_ordered"].sum()),
        "total_pro_to_rdc_rtis": int(active["flow_pro_to_rdc"].sum()),
        "total_rdc_to_pool_rtis": int(active["flow_rdc_to_pool"].sum()),
        "mean_producer_backorders_rtis": round(float(active["producer_backorders"].mean()), 2),
        "mean_pool_backorders_rtis": round(float(active["pool_backorders"].mean()), 2),
        "peak_total_backorders_rtis": int(active["total_backorders"].max()),
        "mean_pool_washed_stock_rtis": round(float(active["pool_washed"].mean()), 2),
        "mean_pool_unwashed_stock_rtis": round(float(active["pool_unwashed"].mean()), 2),
    }
    pd.DataFrame([summary]).to_csv(output / "baseline_summary.csv", index=False)

    line_chart(active, ["pool_washed", "pool_unwashed", "pool_processing_buffer"],
               "Pooler stock and processing buffer", "RTIs", output / "01_pool_inventory.png")
    line_chart(active, ["producer_backorders", "pool_backorders"],
               "Outstanding backorders", "RTIs", output / "02_backorders.png")
    line_chart(active, ["flow_pro_to_rdc", "flow_rdc_to_rpos", "flow_rdc_to_pool"],
               "Major network flows", "RTIs per day", output / "03_flows.png")
    line_chart(active, ["producer_stock", "rpos_display", "rdc_reverse"],
               "Other network stocks", "RTIs", output / "04_network_inventory.png")

    crate_backorders = (
        backlog.loc[backlog["Warehouse"].str.startswith("PRO_")]
        .groupby(["Step", "Crate Type"])["Quantity"]
        .sum().unstack(fill_value=0).reindex(index=steps, fill_value=0)
    )
    line_chart(crate_backorders.loc[crate_backorders.index > 0], list(crate_backorders.columns),
               "Producer backorders by crate type", "RTIs", output / "05_backorders_by_crate_type.png")

    producer_inventory = (
        stock.loc[stock["Warehouse"].str.startswith("PRO_")]
        .groupby(["Step", "Warehouse"])["Quantity"]
        .sum().unstack(fill_value=0).reindex(index=steps, fill_value=0)
    )
    line_chart(producer_inventory.loc[producer_inventory.index > 0], list(producer_inventory.columns),
               "Producer stock by producer", "RTIs", output / "06_producer_inventory.png")

    report = [
        "# Baseline diagnostic notes", "",
        f"Input workbook: `{workbook}`", "",
        "## Automated checks", "",
        f"- Completed steps: {len(active)} (expected 365 for a full run)",
        f"- Initial modeled RTIs: {initial_stock:,} (default expected: {EXPECTED_INITIAL_RTIS:,})",
        f"- Matches professor's default initial RTI total: **{matches_expected}**",
        f"- End-of-day stock conservation: **{stock_conserved}**",
        f"- Every-day PRO->RDC flow equals RDC->RPOS flow: **{rdc_flow_matched}**",
        "", "## Descriptive results", "",
        f"- Mean producer backorders: {summary['mean_producer_backorders_rtis']:,} RTIs",
        f"- Mean pooler backorders: {summary['mean_pool_backorders_rtis']:,} RTIs",
        f"- Peak total backorders: {summary['peak_total_backorders_rtis']:,} RTIs",
        f"- Mean washed stock at pooler: {summary['mean_pool_washed_stock_rtis']:,} RTIs",
        f"- Mean unwashed stock at pooler: {summary['mean_pool_unwashed_stock_rtis']:,} RTIs",
        "", "## Interpretation to complete after examining graphs", "",
        "1. Which crate types and nodes experience persistent stock imbalances?",
        "2. During which days do backorders become highest, and what is happening to pool stock?",
        "3. Do reverse flows appear to constrain recovery throughput?",
        "", "## Limitations of the currently exported data", "",
        "- Shipment throughput is NOT the same as on-time order fill rate: order fulfillment timestamps are missing.",
        "- True RTI reuse cycles and detention-time distributions require RTI-level event/history logging.",
        "- Stock conservation here is based on recorded stock categories; it should also be tested at the agent level.",
        "- A single simulation run cannot establish statistical improvement; future work needs replicated seeded runs.",
        "", "## Next development recommendation", "",
        "Add order-due, fulfilled-on-time, and RTI-level cycle-event counters before comparing traceability policies.",
    ]
    (output / "baseline_findings.md").write_text("\n".join(report) + "\n", encoding="utf-8")

    print(f"Analyzed {len(active)} simulation days from {workbook}")
    print(f"Initial stock matches default: {matches_expected}; stock conserved: {stock_conserved}")
    print(f"Diagnostics written to: {output.resolve()}")


if __name__ == "__main__":
    main()
