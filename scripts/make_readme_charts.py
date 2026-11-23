"""Draw the README charts from the exported marts (run the pipeline first)."""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import MultipleLocator  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
EXPORTS = ROOT / "exports"
OUT = ROOT / "docs" / "images"
BLUE, ORANGE, INK, MUTED, GRID = "#2a78d6", "#eb6834", "#1f1f1f", "#6b6b6b", "#e6e6e6"

plt.rcParams.update({
    "font.size": 11, "axes.edgecolor": GRID, "axes.labelcolor": MUTED, "xtick.color": MUTED,
    "ytick.color": MUTED, "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True,
    "grid.color": GRID, "grid.linewidth": 0.8, "axes.titlesize": 13, "axes.titleweight": "bold",
    "axes.titlelocation": "left", "axes.axisbelow": True, "figure.dpi": 150, "savefig.bbox": "tight",
})


def program_trend() -> None:
    q = pd.read_csv(EXPORTS / "mart_program_quarterly.csv").sort_values("quarter")
    fig, ax = plt.subplots(figsize=(9, 4.2))
    for group, color in [("Program hospitals", BLUE), ("Comparison hospitals", ORANGE)]:
        d = q[q["program_group"] == group]
        ax.plot(d["quarter"], d["readmission_rate"], color=color, linewidth=2, marker="o", markersize=5)
        ax.annotate(group, (d["quarter"].iloc[-1], d["readmission_rate"].iloc[-1]), xytext=(8, 0),
                    textcoords="offset points", va="center", color=INK, fontsize=10)
    start = list(q["quarter"].unique()).index("2025-Q1")
    ax.axvline(start - 0.5, color=MUTED, linestyle="--", linewidth=1)
    ax.text(start - 0.4, ax.get_ylim()[1] * 0.98, "Program starts", color=MUTED, fontsize=9, va="top")
    ax.yaxis.set_major_locator(MultipleLocator(0.02))
    ax.yaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
    ax.set_title("Readmissions for target conditions fell only where the program started")
    ax.set_ylabel("30-day readmission rate")
    ax.tick_params(axis="x", rotation=45)
    ax.grid(axis="x", visible=False)
    fig.savefig(OUT / "program_readmissions.png")
    plt.close(fig)


def risk_adjusted() -> None:
    h = pd.read_csv(EXPORTS / "mart_hospital_readmissions_risk_adjusted.csv").sort_values("oe_ratio", ascending=False)
    fig, ax = plt.subplots(figsize=(8, 3.6))
    colors = [ORANGE if r > 1 else BLUE for r in h["oe_ratio"]]
    ax.barh(h["hospital_name"], h["oe_ratio"] - 1, left=1, color=colors, height=0.6)
    ax.axvline(1, color=INK, linewidth=1)
    for y, r in enumerate(h["oe_ratio"]):
        ax.text(r + (0.006 if r > 1 else -0.006), y, f"{r:.2f}", va="center", ha="left" if r > 1 else "right", fontsize=10)
    ax.set_xlim(0.8, 1.25)
    ax.set_title("Risk-adjusted readmissions: observed / expected")
    ax.set_xlabel("< 1 better than case mix predicts  |  > 1 worse")
    ax.grid(axis="y", visible=False)
    fig.savefig(OUT / "hospital_risk_adjusted.png")
    plt.close(fig)


def lwbs_by_wait() -> None:
    w = pd.read_csv(EXPORTS / "mart_ed_lwbs_by_wait_band.csv")
    labels = w["wait_band"].str.split(". ", n=1).str[1]
    fig, ax = plt.subplots(figsize=(8, 3.8))
    ax.bar(labels, w["lwbs_rate"], color=BLUE, width=0.65)
    for x, r in enumerate(w["lwbs_rate"]):
        ax.text(x, r + 0.002, f"{r:.1%}", ha="center", fontsize=10, color=INK)
    ax.yaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
    ax.set_title("The longer others wait, the more patients leave without being seen")
    ax.set_xlabel("Average wait of patients seen in the same hospital and hour")
    ax.set_ylabel("Left without being seen")
    ax.grid(axis="x", visible=False)
    fig.savefig(OUT / "ed_lwbs_by_wait.png")
    plt.close(fig)


def cost_by_diagnosis() -> None:
    c = pd.read_csv(EXPORTS / "mart_cost_by_diagnosis.csv").nlargest(10, "total_cost_gtq").iloc[::-1]
    fig, ax = plt.subplots(figsize=(8, 4.4))
    ax.barh(c["diagnosis"], c["total_cost_gtq"] / 1e6, color=BLUE, height=0.65)
    for y, (v, a) in enumerate(zip(c["total_cost_gtq"] / 1e6, c["avg_cost_gtq"])):
        ax.text(v + 1, y, f"Q{v:.0f}M  (Q{a / 1000:.0f}k per stay)", va="center", fontsize=9, color=INK)
    ax.set_xlim(0, c["total_cost_gtq"].max() / 1e6 * 1.45)
    ax.set_title("Where the money goes: total cost by diagnosis, 2023-2026")
    ax.set_xlabel("Million GTQ")
    ax.grid(axis="y", visible=False)
    fig.savefig(OUT / "cost_by_diagnosis.png")
    plt.close(fig)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    program_trend()
    risk_adjusted()
    lwbs_by_wait()
    cost_by_diagnosis()
    print(f"Charts written to {OUT.relative_to(ROOT)}")
