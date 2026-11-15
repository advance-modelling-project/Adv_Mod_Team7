"""Visualise CLSC effectiveness, efficiency, and circularity KPIs.

Example (run inside Adv_Mod):
    python analysis/visualize_operational_kpis.py --input run_2026.10.25_22.10/sim_log_2026.10.25_22.10.xlsx

The simulation export records daily RTI quantities, not vehicle-departure
events. Therefore truck departures are *estimated* as ceil(daily RTIs / truck
capacity in RTIs). RDC -> POOL is the exception: its model logic ships only
full trucks, so this estimate matches the recorded movement rule.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


REQUIRED = {"Stock", "Flows", "Backorders"}


def find_workbook(input_path: str | None) -> Path:
    if input_path:
        path = Path(input_path)
        if not path.exists():
            raise FileNotFoundError(f"Workbook not found: {path}")
        return path
    matches = list(Path.cwd().glob("run_*/sim_log_*.xlsx"))
    if not matches:
        raise FileNotFoundError("No run workbook found. Supply --input.")
    return max(matches, key=lambda p: p.stat().st_mtime)


def node_group(warehouse: str) -> str:
    if warehouse.startswith("POOL_"):
        return "POOL"
    if warehouse.startswith("PRO_"):
        return warehouse
    if warehouse.startswith("RDC_"):
        return "RDC"
    if warehouse.startswith("RPOS_"):
        return "RPOS"
    return warehouse


def is_service_stock(warehouse: str) -> bool:
    """True only for inventory that can directly support an outbound order/service."""
    return warehouse.startswith("PRO_") or warehouse in {"POOL_WASHED", "POOL_UNWASHED", "RPOS_DISPLAY"}


def make_summary(stock: pd.DataFrame, flows: pd.DataFrame, backlog: pd.DataFrame,
                 truck_capacity_rtis: int) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    relevant = stock.groupby(["Warehouse", "Crate Type"])["Quantity"].max().gt(0)
    relevant = relevant[relevant].index
    stock = stock.set_index(["Warehouse", "Crate Type"]).loc[relevant].reset_index()
    stock["Node"] = stock["Warehouse"].map(node_group)
    availability = stock.groupby(["Warehouse", "Crate Type"], as_index=False).agg(
        average_inventory=("Quantity", "mean"),
        minimum_inventory=("Quantity", "min"),
        zero_inventory_days=("Quantity", lambda x: int((x == 0).sum())),
        inventory_cv=("Quantity", lambda x: x.std(ddof=0) / x.mean() if x.mean() else np.nan),
    )
    availability["zero_inventory_rate_pct"] = 100 * availability["zero_inventory_days"] / stock["Step"].nunique()
    availability["is_service_stock"] = availability["Warehouse"].map(is_service_stock)

    route_day = flows.groupby(["Step", "Origin", "Destination"], as_index=False)["Quantity"].sum()
    route_day["Route"] = route_day["Origin"] + " → " + route_day["Destination"]
    route_day["estimated_truck_departures"] = np.ceil(route_day["Quantity"] / truck_capacity_rtis).astype(int)
    circularity = route_day.groupby("Route", as_index=False).agg(
        active_days=("Quantity", lambda x: int((x > 0).sum())),
        total_rtis=("Quantity", "sum"),
        mean_rtis_per_active_day=("Quantity", lambda x: x[x > 0].mean()),
        peak_rtis_per_day=("Quantity", "max"),
        estimated_truck_departures=("estimated_truck_departures", "sum"),
    )
    circularity["mean_trucks_per_active_day"] = (
        circularity["estimated_truck_departures"] / circularity["active_days"].replace(0, np.nan)
    )
    backlog_daily = backlog.groupby("Step", as_index=False)["Quantity"].sum()
    return availability, circularity, backlog_daily


def draw_dashboard(stock: pd.DataFrame, flows: pd.DataFrame, availability: pd.DataFrame,
                   circularity: pd.DataFrame, backlog: pd.DataFrame, output: Path,
                   workbook: Path) -> None:
    stock["Node"] = stock["Warehouse"].map(node_group)
    node_inventory = stock.groupby(["Step", "Node"], as_index=False)["Quantity"].sum()
    daily_flow = flows.groupby("Step", as_index=False)["Quantity"].sum()
    # Reverse, buffer, and transit-adjacent stocks can normally be zero while batches form.
    # They are useful for efficiency analysis, but not evidence of a service stockout.
    service_availability = availability[availability["is_service_stock"]].copy()
    risk = service_availability.sort_values("zero_inventory_days", ascending=False).head(15)
    routes = circularity.sort_values("estimated_truck_departures", ascending=False).head(12)
    heat = service_availability.pivot(index="Warehouse", columns="Crate Type", values="zero_inventory_rate_pct").fillna(0)

    plt.style.use("seaborn-v0_8-whitegrid")
    fig, axes = plt.subplots(2, 3, figsize=(19, 10), constrained_layout=True)
    fig.suptitle(f"Operational KPI dashboard: effectiveness, efficiency, circularity\n{workbook.name}",
                 fontsize=16, fontweight="bold")

    ax = axes[0, 0]
    for node, value in node_inventory.groupby("Node"):
        ax.plot(value["Step"], value["Quantity"], linewidth=1.8, label=node)
    ax.set(title="Efficiency: inventory by network node", xlabel="Step", ylabel="RTIs")
    ax.legend(fontsize=7, ncol=2)

    ax = axes[0, 1]
    labels = risk["Warehouse"] + " | " + risk["Crate Type"]
    ax.barh(labels.iloc[::-1], risk["zero_inventory_days"].iloc[::-1], color="#c44e52")
    ax.set(title="Effectiveness: service-stock zero exposure", xlabel="Days at zero inventory", ylabel="")

    ax = axes[0, 2]
    image = ax.imshow(heat.to_numpy(), cmap="YlOrRd", aspect="auto", vmin=0, vmax=max(1, heat.to_numpy().max()))
    ax.set(title="Effectiveness: service-stock zero rate", xlabel="Crate type", ylabel="Warehouse")
    ax.set_xticks(range(len(heat.columns)), heat.columns, rotation=30, ha="right")
    ax.set_yticks(range(len(heat.index)), heat.index, fontsize=8)
    fig.colorbar(image, ax=ax, label="% of simulated days", pad=0.02)

    ax = axes[1, 0]
    ax.plot(backlog["Step"], backlog["Quantity"], color="#c44e52", linewidth=2)
    ax.fill_between(backlog["Step"], backlog["Quantity"], color="#c44e52", alpha=0.2)
    ax.set(title="Effectiveness: due-order backlog", xlabel="Step", ylabel="RTIs")
    ax.set_ylim(bottom=0)

    ax = axes[1, 1]
    ax.barh(routes["Route"].iloc[::-1], routes["estimated_truck_departures"].iloc[::-1], color="#4c72b0")
    ax.set(title="Circularity: estimated dispatches by route", xlabel="Estimated truck departures", ylabel="")

    ax = axes[1, 2]
    ax.plot(daily_flow["Step"], daily_flow["Quantity"], color="#55a868", linewidth=1.4)
    ax.axhline(daily_flow["Quantity"].mean(), color="#333333", linestyle="--",
               label=f"Mean: {daily_flow['Quantity'].mean():,.0f} RTIs/day")
    ax.set(title="Circularity: daily movement intensity", xlabel="Step", ylabel="RTIs/day")
    ax.legend(fontsize=8)

    fig.savefig(output, dpi=180, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyse operational KPIs of a CLSC run.")
    parser.add_argument("--input", help="Path to sim_log_*.xlsx; newest run is used by default.")
    parser.add_argument("--outdir", help="Output directory; defaults to <run>/operational_kpis.")
    parser.add_argument("--truck-capacity-uls", type=int, default=33, help="Truck capacity in ULs (default: 33).")
    parser.add_argument("--ul-size", type=int, default=200, help="RTIs per UL (default: 200).")
    args = parser.parse_args()
    if args.truck_capacity_uls <= 0 or args.ul_size <= 0:
        raise ValueError("Truck capacity and UL size must be positive.")

    workbook = find_workbook(args.input)
    sheet_names = set(pd.ExcelFile(workbook).sheet_names)
    missing = REQUIRED - sheet_names
    if missing:
        raise ValueError(f"Missing required sheets: {sorted(missing)}")
    stock = pd.read_excel(workbook, sheet_name="Stock")
    flows = pd.read_excel(workbook, sheet_name="Flows")
    backlog = pd.read_excel(workbook, sheet_name="Backorders")
    output_dir = Path(args.outdir) if args.outdir else workbook.parent / "operational_kpis"
    output_dir.mkdir(parents=True, exist_ok=True)
    truck_capacity_rtis = args.truck_capacity_uls * args.ul_size

    availability, circularity, backlog_daily = make_summary(stock, flows, backlog, truck_capacity_rtis)
    availability.to_csv(output_dir / "availability_and_inventory_risk.csv", index=False, encoding="utf-8-sig")
    circularity.to_csv(output_dir / "route_dispatch_frequency.csv", index=False, encoding="utf-8-sig")
    draw_dashboard(stock, flows, availability, circularity, backlog_daily,
                   output_dir / "operational_kpi_dashboard.png", workbook)
    print(f"Dashboard: {output_dir / 'operational_kpi_dashboard.png'}")
    print(f"Availability detail: {output_dir / 'availability_and_inventory_risk.csv'}")
    print(f"Dispatch-frequency detail: {output_dir / 'route_dispatch_frequency.csv'}")
    print("NOTE: dispatch counts are capacity-based estimates; only RDC -> POOL is modelled as full-truck dispatches.")


if __name__ == "__main__":
    main()
