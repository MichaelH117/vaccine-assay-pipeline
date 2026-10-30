"""Showcase infographics for the README (Principal Engineer seat). Run from the repo root:

    .venv/Scripts/python tools/make_showcase_figures.py

Reads only recorded run outputs: docs/results.json, docs/evidence/repeat_run_summary.json and
docs/evidence/scale_*.json. Writes three PNGs to docs/img/. Every figure is labelled synthetic. The charts use an
opaque light surface so they stay readable on both light and dark GitHub themes.
"""
import json
from pathlib import Path

import matplotlib
import matplotlib.ticker

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
IMG = ROOT / "docs" / "img"
EVID = ROOT / "docs" / "evidence"

SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
BLUE, GRAY, GOOD, CRIT = "#2a78d6", "#b9b8b0", "#0ca30c", "#d03b3b"

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "text.color": INK, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "axes.edgecolor": GRID, "font.size": 11, "font.family": "DejaVu Sans",
})


def scorecard(results: dict) -> Path:
    s = results["summary"]
    rows, seen = [], set()
    for r in s["scorecard"]:
        if r["problem_id"] in seen:          # INJ-2 is one problem with two records
            rows[-1]["keys"].append(r["affected_key"])
            continue
        seen.add(r["problem_id"])
        rows.append({"pid": r["problem_id"], "inj": r["inj_type"], "keys": [r["affected_key"]],
                     "desc": r["description"].split(" (")[0].replace("`", ""), "by": r["caught_by"] or "MISSED",
                     "ok": bool(r["problem_detected"])})
    n = len(rows)
    fig, ax = plt.subplots(figsize=(13, 0.48 * n + 2.0))
    ax.set_xlim(0, 100)
    ax.set_ylim(n + 0.2, -1.6)
    ax.axis("off")
    head = s["scorecard_summary"]["headline"].split(";")[0]
    fp = s["false_positives"]
    fig.suptitle(f"Detection scorecard: {head} (synthetic data, seed {results['seed']})",
                 x=0.012, ha="left", fontsize=14, fontweight="bold")
    for x, t in ((0, "Problem"), (9, "Type"), (17, "Planted on"), (35, "What was planted"), (74, "Caught by")):
        ax.text(x, -0.9, t, fontsize=10, color=INK2, fontweight="bold")
    for i, r in enumerate(rows):
        if i % 2 == 0:
            ax.axhspan(i - 0.5, i + 0.5, color="#f1f0ec", zorder=0)
        ax.text(0, i, r["pid"], va="center", fontsize=10)
        ax.text(9, i, r["inj"], va="center", fontsize=10)
        ax.text(17, i, " + ".join(r["keys"]), va="center", fontsize=10)
        desc = r["desc"] if len(r["desc"]) <= 52 else r["desc"][:50] + "..."
        ax.text(35, i, desc, va="center", fontsize=10, color=INK2)
        ax.text(74, i, ("✓ " if r["ok"] else "✗ ") + r["by"].replace(",", " + "), va="center",
                fontsize=10, color=GOOD if r["ok"] else CRIT, fontweight="bold")
    fig.text(0.012, 0.012,
             f"Guardrails: {fp['samples_with_unexplained_flag']} of {fp['samples_total']} samples carry a flag no "
             f"planted problem explains (SMP-00180, a second catch of INJ-7; see FLAW_HUNT FH-05); "
             f"{fp['plates_rejected_unexplained']} of {fp['plates_total']} plates rejected without a planted cause.",
             fontsize=9.5, color=INK2)
    out = IMG / "detection_scorecard.png"
    fig.savefig(out, dpi=110, bbox_inches="tight", pad_inches=0.25)
    plt.close(fig)
    return out


def repeat_run(ev: dict) -> Path:
    bars = [("Output files\n(SHA-256)", ev["files_identical"], len(ev["files_different"]), 0, ev["files_hashed"]),
            ("DuckDB tables\n(row content)", ev["db_tables_identical"], ev["db_tables_run_clock_only"],
             ev["db_tables_other_differences"], ev["db_tables"])]
    fig, ax = plt.subplots(figsize=(11, 3.8))
    for y, (_label, same, clock, other, total) in enumerate(bars):
        ax.barh(y, same / total * 100, color=BLUE, height=0.5, edgecolor=SURFACE, linewidth=2)
        ax.barh(y, clock / total * 100, left=same / total * 100, color=GRAY, height=0.5, hatch="//",
                edgecolor=SURFACE, linewidth=2)
        ax.text(1.5, y, f"{same} of {total} identical", va="center", color="white", fontweight="bold")
        ax.text(100, y - 0.3, f"{clock} differ only in run-clock columns; {other} other differences",
                va="bottom", ha="right", fontsize=9.5, color=INK2)
    ax.set_yticks(range(len(bars)), [b[0] for b in bars])
    ax.set_ylim(1.45, -0.75)
    # y axis already runs top-down via set_ylim
    ax.set_xlim(0, 100)
    ax.set_xlabel("% of items")
    ax.grid(axis="x", color=GRID)
    ax.set_axisbelow(True)
    for sp in ("top", "right", "left"):
        ax.spines[sp].set_visible(False)
    ax.set_title(f"Same seed, two runs: what changed? ({ev['date']}, synthetic data)", loc="left",
                 fontsize=13, fontweight="bold")
    fig.text(0.01, 0.01, "Run-clock columns are audit timestamps, hashes over them, and the 13 raw-file audit payloads "
             "that include ingest time. Evidence: docs/evidence/.", fontsize=9, color=INK2)
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    out = IMG / "repeat_run_check.png"
    fig.savefig(out, dpi=110)
    plt.close(fig)
    return out


def scale(profiles: list[dict]) -> Path:
    names = ["generate", "load LIMS (audited)", "ingest plates", "4PL fits", "QC", "reportable selection",
             "integrity checks", "dbt build + tests"]
    fig, ax = plt.subplots(figsize=(12, 6.0))
    colors = [BLUE, "#eb6834", "#1baf7a"]
    h = 0.8 / len(profiles)
    for k, p in enumerate(profiles):
        t = [m[0] for m in p["step_marks_s"]] + [p["total_s"]]
        dur = [round(t[i + 1] - t[i], 1) for i in range(len(names))]
        ys = [i + (k - (len(profiles) - 1) / 2) * h for i in range(len(names))]
        ax.barh(ys, dur, height=h * 0.9, color=colors[k], edgecolor=SURFACE, linewidth=1,
                label=f"{p['factor']}x: {p['samples']:,} samples, {p['plates']} plates, {p['total_s']} s total")
        for y, d in zip(ys, dur, strict=True):
            ax.text(d * 1.08, y, f"{d} s", va="center", fontsize=8, color=INK2)
    ax.set_yticks(range(len(names)), names)
    ax.invert_yaxis()
    ax.set_xscale("log")
    ax.set_xlim(0.05, 600)
    ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:g}"))
    ax.set_xlabel("seconds, log scale (measured on a 16 GB laptop, clean build, no pytest)")
    ax.grid(axis="x", color=GRID)
    ax.set_axisbelow(True)
    for sp in ("top", "right", "left"):
        ax.spines[sp].set_visible(False)
    ax.legend(frameon=False, loc="upper center", bbox_to_anchor=(0.45, -0.13), ncol=3, fontsize=9)
    ax.set_title("Where the time goes as the study grows (synthetic data)", loc="left", fontsize=13,
                 fontweight="bold")
    fig.tight_layout()
    out = IMG / "scale_profile.png"
    fig.savefig(out, dpi=110)
    plt.close(fig)
    return out


if __name__ == "__main__":
    results = json.loads((ROOT / "docs" / "results.json").read_text())
    print(scorecard(results))
    print(repeat_run(json.loads((EVID / "repeat_run_summary.json").read_text())))
    profiles = [json.loads(p.read_text()) for p in sorted(EVID.glob("scale_*x.json"),
                                                          key=lambda p: int(p.stem.split("_")[1][:-1]))]
    profiles = [p for p in profiles if "step_marks_s" in p]
    print(scale(profiles))
