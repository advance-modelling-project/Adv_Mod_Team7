"""Create a KPI summary and dashboard from a CLSC simulation workbook.

Run from the Adv_Mod directory, for example:
    python analysis/visualize_kpis.py --input run_2026.10.25_22.10/sim_log_2026.10.25_22.10.xlsx

The script works with the baseline export (Stock, Flows, Backorders, Orders)
and adds screening and fulfilment charts automatically when those optional
sheets are present in a newer simulation run.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm
import numpy as np
import pandas as pd


REQUIRED_SHEETS = {"Stock", "Flows", "Backorders", "Orders"}


def locate_workbook(path_text: str | None) -> Path:
    if path_text:
        path = Path(path_text)
        if not path.exists():
            raise FileNotFoundError(f"Workbook not found: {path}")
        return path
    candidates = list(Path.cwd().glob("run_*/sim_log_*.xlsx"))
    if not candidates:
        raise FileNotFoundError("No sim_log_*.xlsx found. Supply --input.")
    return max(candidates, key=lambda p: p.stat().st_mtime)


def classify_location(location: str) -> str:
    if location.startswith("PRO_"):
        return "Producers"
    if location.startswith("RPOS_"):
        return "Retail POS"
    if location.startswith("RDC_"):
        return "RDC"
    if location.startswith("POOL_"):
        return "Pool"
    return location


def load_data(workbook: Path) -> tuple[dict[str, pd.DataFrame], set[str]]:
    excel = pd.ExcelFile(workbook)
    sheets = set(excel.sheet_names)
    missing = REQUIRED_SHEETS - sheets
    if missing:
        raise ValueError(f"Missing required sheets: {sorted(missing)}")
    return {sheet: pd.read_excel(workbook, sheet_name=sheet) for sheet in sheets}, sheets


def kpi_table(data: dict[str, pd.DataFrame], sheets: set[str]) -> pd.DataFrame:
    stock = data["Stock"].copy()
    flows = data["Flows"].copy()
    backorders = data["Backorders"].copy()
    orders = data["Orders"].copy()
    stock["Location group"] = stock["Warehouse"].map(classify_location)
    daily_flow = flows.groupby("Step", as_index=False)["Quantity"].sum()
    daily_backorders = backorders.groupby("Step", as_index=False)["Quantity"].sum()
    final_step = int(stock["Step"].max())
    initial_total = int(stock.loc[stock["Step"] == stock["Step"].min(), "Quantity"].sum())
    final_total = int(stock.loc[stock["Step"] == final_step, "Quantity"].sum())
    metrics = [
        ("Horizon", "days", final_step, "Last simulated step (step 0 is an initial snapshot)."),
        ("Initial on-hand inventory", "RTIs", initial_total, "All recorded node inventories at step 0."),
        ("Final on-hand inventory", "RTIs", final_total, "All recorded node inventories at the final step; excludes items in transit."),
        ("Inventory change", "RTIs", final_total - initial_total, "Final minus initial recorded on-hand inventory."),
        ("Total recorded movements", "RTIs", int(flows["Quantity"].sum()), "Sum of all daily movements; a crate can be counted on multiple legs."),
        ("Average daily movements", "RTIs/day", float(daily_flow["Quantity"].mean()), "Mean daily volume across all network legs."),
        ("Peak daily movements", "RTIs/day", int(daily_flow["Quantity"].max()), "Largest total movement volume on one day."),
        ("Peak backlog", "RTIs", int(daily_backorders["Quantity"].max()), "Largest outstanding due quantity recorded."),
        ("Final backlog", "RTIs", int(daily_backorders.iloc[-1]["Quantity"]), "Outstanding due quantity at the end of the run."),
        ("Orders created", "orders", int(len(orders)), "Order lines generated during the horizon."),
        ("Mean requested lead time", "days", float(orders["Lead Time"].mean()), "Mean requested order lead time."),
    ]
    if "Screening" in sheets:
        screening = data["Screening"].query("Step > 0")
        arrived = screening["arrived_uls"].sum()
        capacity = screening["capacity_uls"].sum()
        metrics.extend([
            ("Screening capacity utilization", "%", 100 * screening["screened_uls"].sum() / capacity if capacity else np.nan,
             "Screened ULs divided by available screening capacity."),
            ("Screening bypass rate", "%", 100 * screening["bypassed_uls"].sum() / arrived if arrived else np.nan,
             "Bypassed ULs divided by ULs arriving at the pool."),
        ])
    if "Fulfillment" in sheets:
        fulfillment = data["Fulfillment"].iloc[-1]
        for stream in ("producer", "pooler"):
            due = fulfillment.get(f"{stream}_due_rtis", 0)
            on_time = fulfillment.get(f"{stream}_on_time_rtis", 0)
            metrics.append((f"{stream.title()} on-time fill rate", "%", 100 * on_time / due if due else np.nan,
                            "On-time delivered RTIs divided by RTIs due by the end of the horizon."))
    return pd.DataFrame(metrics, columns=["KPI", "Unit", "Value", "Definition"])


def build_dashboard(data: dict[str, pd.DataFrame], workbook: Path, output: Path) -> None:
    stock, flows, backorders = (data[name].copy() for name in ("Stock", "Flows", "Backorders"))
    stock["Location group"] = stock["Warehouse"].map(classify_location)
    stock_grouped = stock.groupby(["Step", "Location group"], as_index=False)["Quantity"].sum()
    daily_flow = flows.groupby(["Step", "Origin", "Destination"], as_index=False)["Quantity"].sum()
    routes = daily_flow.assign(Route=lambda x: x["Origin"] + " → " + x["Destination"])
    route_total = routes.groupby("Route")["Quantity"].sum().sort_values(ascending=False)
    backlog = backorders.groupby("Step", as_index=False)["Quantity"].sum()
    final_stock = stock.loc[stock["Step"] == stock["Step"].max()].pivot_table(
        index="Warehouse", columns="Crate Type", values="Quantity", aggfunc="sum", fill_value=0
    )

    plt.style.use("seaborn-v0_8-whitegrid")
    fig, axes = plt.subplots(2, 3, figsize=(18, 10), constrained_layout=True)
    fig.suptitle(f"Closed-loop supply chain KPI dashboard\n{workbook.name}", fontsize=16, fontweight="bold")

    ax = axes[0, 0]
    for group, values in stock_grouped.groupby("Location group"):
        ax.plot(values["Step"], values["Quantity"], linewidth=2, label=group)
    ax.set(title="On-hand inventory by network stage", xlabel="Step", ylabel="RTIs")
    ax.legend(fontsize=8, ncol=2)

    ax = axes[0, 1]
    top_routes = route_total.head(8).index
    for route in top_routes:
        values = routes[routes["Route"] == route]
        ax.plot(values["Step"], values["Quantity"].cumsum(), label=route)
    ax.set(title="Cumulative flow on busiest routes", xlabel="Step", ylabel="Cumulative RTIs")
    ax.legend(fontsize=7, loc="upper left")

    ax = axes[0, 2]
    ax.plot(backlog["Step"], backlog["Quantity"], color="#c44e52", linewidth=2)
    ax.fill_between(backlog["Step"], backlog["Quantity"], color="#c44e52", alpha=0.2)
    ax.set(title="Outstanding backorders", xlabel="Step", ylabel="RTIs")

    ax = axes[1, 0]
    route_total.head(12).sort_values().plot.barh(ax=ax, color="#4c72b0")
    ax.set(title="Total flow by route", xlabel="RTIs", ylabel="")

    ax = axes[1, 1]
    image_data = final_stock.to_numpy(dtype=float)
    positive = image_data[image_data > 0]
    norm = LogNorm(vmin=max(1, positive.min()), vmax=max(1, positive.max())) if len(positive) else None
    image = ax.imshow(image_data, aspect="auto", cmap="YlGnBu", norm=norm)
    ax.set(title="Final inventory by node and crate type", xlabel="Crate type", ylabel="Warehouse")
    ax.set_xticks(range(len(final_stock.columns)), final_stock.columns, rotation=30, ha="right")
    ax.set_yticks(range(len(final_stock.index)), final_stock.index, fontsize=8)
    fig.colorbar(image, ax=ax, label="RTIs", pad=0.02)

    ax = axes[1, 2]
    daily_total = flows.groupby("Step")["Quantity"].sum()
    ax.plot(daily_total.index, daily_total.values, color="#55a868", linewidth=1.5)
    ax.axhline(daily_total.mean(), color="#333333", linestyle="--", label=f"Mean: {daily_total.mean():,.0f}")
    ax.set(title="Daily network movements", xlabel="Step", ylabel="RTIs/day")
    ax.legend(fontsize=8)

    fig.savefig(output, dpi=180, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description="Visualise KPIs from a CLSC simulation log.")
    parser.add_argument("--input", help="Path to sim_log_*.xlsx. Defaults to the newest run.")
    parser.add_argument("--outdir", help="Output directory. Defaults to <workbook folder>/kpi_analysis.")
    args = parser.parse_args()

    workbook = locate_workbook(args.input)
    output_dir = Path(args.outdir) if args.outdir else workbook.parent / "kpi_analysis"
    output_dir.mkdir(parents=True, exist_ok=True)
    data, sheets = load_data(workbook)
    summary = kpi_table(data, sheets)
    summary.to_csv(output_dir / "kpi_summary.csv", index=False, encoding="utf-8-sig")
    build_dashboard(data, workbook, output_dir / "kpi_dashboard.png")
    print(f"Dashboard: {output_dir / 'kpi_dashboard.png'}")
    print(f"KPI table: {output_dir / 'kpi_summary.csv'}")
    print(summary.to_string(index=False, float_format=lambda x: f"{x:,.2f}"))


if __name__ == "__main__":
    main()
