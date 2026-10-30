"""Static PNG charts for the README (owner: LIA, AC-11.4). matplotlib only, Agg backend, no display needed.

1. gmt_by_group_visit.png  - Does the vaccine raise antibodies? GMT/GMC by group x visit with 95% CI bars.
2. plate_4pl_curve.png     - Is the standard curve trustworthy? One accepted plate's 4PL fit with its standards.
3. plate_status_grid.png   - Which plates passed QC, and why did the others fail?

Colors: reference categorical palette slots 1-2 for the two groups; status colors (good / critical) for plate status,
always paired with a text label so color never carries meaning alone.
"""

from __future__ import annotations

import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.ticker  # noqa: E402,F401
import numpy as np  # noqa: E402

GROUP_COLORS = {"Vaccine": "#2a78d6", "Placebo": "#eb6834"}
STATUS_COLORS = {"ACCEPTED": "#0ca30c", "REJECTED": "#d03b3b"}
INK = "#0b0b0b"
INK_2 = "#52514e"
GRID = "#e4e3df"
SURFACE = "#fcfcfb"
UNIT = "AU/mL"


def _style(ax) -> None:
    ax.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(INK_2)
    ax.tick_params(colors=INK_2)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def _four_pl(x, a, b, c, d):
    # ADR 004 model; kept local so charts do not depend on the fitting module's internals
    return d + (a - d) / (1.0 + (np.asarray(x, dtype=float) / c) ** b)


def chart_gmt(con, path: Path) -> Path:
    df = con.execute(
        "select group_name, visit, visit_day, n, gmt, gmt_lcl, gmt_ucl "
        "from marts.mart_immunogenicity order by visit_day, group_name"
    ).df()
    visits = list(dict.fromkeys(df["visit"]))
    groups = [g for g in ("Vaccine", "Placebo") if g in set(df["group_name"])]
    groups += sorted(set(df["group_name"]) - set(groups))
    width = 0.8 / max(len(groups), 1)
    fig, ax = plt.subplots(figsize=(8, 4.8), dpi=150, facecolor=SURFACE)
    _style(ax)
    x = np.arange(len(visits))
    for i, g in enumerate(groups):
        sub = df[df["group_name"] == g].set_index("visit").reindex(visits)
        gmt = sub["gmt"].to_numpy(dtype=float)
        lo = np.nan_to_num(gmt - sub["gmt_lcl"].to_numpy(dtype=float), nan=0.0)
        hi = np.nan_to_num(sub["gmt_ucl"].to_numpy(dtype=float) - gmt, nan=0.0)
        pos = x + (i - (len(groups) - 1) / 2) * width
        ax.bar(pos, gmt, width=width * 0.92, color=GROUP_COLORS.get(g, "#6250d6"), label=g,
               edgecolor=SURFACE, linewidth=1)
        ax.errorbar(pos, gmt, yerr=[lo, hi], fmt="none", ecolor=INK, elinewidth=1, capsize=3)
        ucl = sub["gmt_ucl"].to_numpy(dtype=float)
        top = np.where(np.isnan(ucl), gmt, ucl)
        for p, v, t, n in zip(pos, gmt, top, sub["n"].to_numpy(), strict=True):
            if not math.isnan(v):  # label above the upper CI so it never sits on the error bar
                ax.annotate(f"{v:,.0f}\nn={int(n)}", (p, t), xytext=(0, 4), textcoords="offset points",
                            ha="center", va="bottom", fontsize=7, color=INK_2)
    ax.set_yscale("log")
    ax.margins(y=0.15)
    plain = matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:,.0f}")
    ax.yaxis.set_major_formatter(plain)
    # label only the 2x and 5x minor ticks so the log axis stays readable
    ax.yaxis.set_minor_formatter(matplotlib.ticker.FuncFormatter(
        lambda v, _: f"{v:,.0f}" if f"{v:.0e}"[0] in "25" else ""))
    ax.set_xticks(x, [f"{v} (day {int(d)})" for v, d in
                      df.drop_duplicates("visit").set_index("visit").reindex(visits)["visit_day"].items()])
    ax.set_xlabel("Visit", color=INK)
    ax.set_ylabel(f"GMT/GMC ({UNIT}, log scale)", color=INK)
    ax.set_title("Anti-Antigen X IgG GMT/GMC by group and visit, with 95% CI (synthetic data)", color=INK,
                 fontsize=10, loc="left")
    ax.legend(frameon=False, title="Group")
    fig.tight_layout()
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)
    return path


def chart_curve(con, path: Path) -> Path:
    fit = con.execute(
        "select f.plate_id, f.a, f.b, f.c, f.d, f.r_squared, f.lloq_conc, f.uloq_conc "
        "from assay.curve_fits f join assay.plate_status s using (plate_id) "
        "where s.status = 'ACCEPTED' and f.converged order by f.plate_id limit 1"
    ).df()
    if fit.empty:
        raise ValueError("no accepted plate with a converged fit to plot")
    f = fit.iloc[0]
    pts = con.execute(
        "select m.nominal_conc, w.od_blank_corrected as od from assay.well_reads w "
        "join assay.plate_map m on m.plate_id = w.plate_id and m.well = w.well "
        "where m.well_type = 'STD' and w.plate_id = ? order by m.nominal_conc",
        [f["plate_id"]],
    ).df()
    fig, ax = plt.subplots(figsize=(7, 4.8), dpi=150, facecolor=SURFACE)
    _style(ax)
    xs = np.geomspace(pts["nominal_conc"].min() / 2, pts["nominal_conc"].max() * 2, 300)
    ax.plot(xs, _four_pl(xs, f["a"], f["b"], f["c"], f["d"]), color=GROUP_COLORS["Vaccine"], linewidth=2,
            label=f"4PL fit (R² = {f['r_squared']:.4f})")
    ax.scatter(pts["nominal_conc"], pts["od"], s=36, color=INK, zorder=3, label="Standard wells (duplicates)",
               edgecolor=SURFACE, linewidth=1)
    for val, name in ((f["lloq_conc"], "LLOQ"), (f["uloq_conc"], "ULOQ")):
        if val is not None and not (isinstance(val, float) and math.isnan(val)):
            ax.axvline(val, color=INK_2, linestyle="--", linewidth=1)
            ax.annotate(f"{name} {val:g}", (val, 0.5), xycoords=("data", "axes fraction"), xytext=(3, 0),
                        textcoords="offset points", fontsize=8, color=INK_2, rotation=90, va="center")
    ax.set_xscale("log")
    ax.set_xlabel(f"Nominal concentration ({UNIT}, curve units before dilution, log scale)", color=INK)
    ax.set_ylabel("Optical density, blank-corrected (OD)", color=INK)
    ax.set_title(f"Standard curve, {f['plate_id']}: 4PL fit and standards (synthetic data)", color=INK,
                 fontsize=10, loc="left")
    ax.legend(frameon=False, loc="lower right")
    fig.tight_layout()
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)
    return path


def chart_plate_grid(con, path: Path) -> Path:
    df = con.execute(
        "select s.plate_id, s.status, coalesce(s.reject_reasons, '') as reject_reasons, r.repeat_of_plate_id "
        "from assay.plate_status s left join lims.plate_runs r using (plate_id) order by s.plate_id"
    ).df()
    n = len(df)
    cols = min(6, max(n, 1))
    rows = max(math.ceil(n / cols), 1)
    fig, ax = plt.subplots(figsize=(1.7 * cols + 0.6, 1.3 * rows + 1.2), dpi=150, facecolor=SURFACE)
    ax.set_facecolor(SURFACE)
    for i, r in enumerate(df.itertuples(index=False)):
        cx, cy = i % cols, rows - 1 - i // cols
        ax.add_patch(plt.Rectangle((cx + 0.04, cy + 0.06), 0.92, 0.88, color=STATUS_COLORS.get(r.status, INK_2),
                                   linewidth=0))
        # one rule per line so long reason lists stay inside the tile
        lines = [r.plate_id, r.status] + [x.strip() for x in r.reject_reasons.split(",") if x.strip()]
        if isinstance(r.repeat_of_plate_id, str) and r.repeat_of_plate_id:
            lines.append(f"(repeat of {r.repeat_of_plate_id})")
        ax.text(cx + 0.5, cy + 0.5, "\n".join(lines), ha="center", va="center", fontsize=7, color="#ffffff",
                fontweight="bold")
    ax.set_xlim(0, cols)
    ax.set_ylim(0, rows)
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(False)
    n_rej = int((df["status"] == "REJECTED").sum())
    ax.set_title(f"Plate QC status: {n - n_rej} accepted, {n_rej} rejected of {n} plates (synthetic data)",
                 color=INK, fontsize=10, loc="left")
    ax.set_xlabel("Each tile is one 96-well plate; rejected tiles list the failed plate rules", color=INK_2,
                  fontsize=8)
    fig.tight_layout()
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)
    return path


def render_charts(con, out: Path) -> list[Path]:
    """Render the 3 README charts into `out` (docs/img/). Returns the PNG paths."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    return [
        chart_gmt(con, out / "gmt_by_group_visit.png"),
        chart_curve(con, out / "plate_4pl_curve.png"),
        chart_plate_grid(con, out / "plate_status_grid.png"),
    ]
