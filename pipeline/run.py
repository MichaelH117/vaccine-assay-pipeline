"""One command: generate the synthetic study, load the mini-LIMS, ingest plates, fit curves, QC, pick reportable
results, tamper (INJ-7) and verify integrity, run dbt, export marts, draw charts, write results.

Run: python -m pipeline.run [--seed 42] [--test] [--optional-problems]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import time
from pathlib import Path

import duckdb
import pandas as pd

from generator.generate import generate, write
from pipeline.audit import verify_chain
from pipeline.config import ROOT, Paths, dbt_vars, default_paths, load_rules
from pipeline.curve import fit_all
from pipeline.ingest import ingest_plates, make_writable
from pipeline.integrity import reconcile_records, rehash_raw_files, write_chain_anchor, write_chain_verify
from pipeline.lims_load import load_lims, read_landing
from pipeline.qc import run_qc
from pipeline.reportable import select_reportable
from pipeline.schema import create_schema

RESULTS = ROOT / "docs" / "results.json"
LAST_DBT: dict = {}   # counts from the most recent build()'s dbt run (build() returns Paths, per DESIGN 4)
TRUTH_COLS = ["problem_id", "inj_type", "key_type", "affected_key", "description"]


def anchor_path(paths: Paths) -> Path:
    """GXP's write-once, read-only chain-head anchor (BUG-004), kept outside the DuckDB file."""
    return paths.db.parent / "audit_anchor.json"


def _clean(paths: Paths) -> None:
    """Remove last run's generated data. Raw copies and the anchor are read-only, so make them writable first
    (DESIGN R6)."""
    for folder in (paths.landing, paths.raw):
        if folder.exists():
            make_writable(folder)
            shutil.rmtree(folder)
    for f in (paths.db, paths.db.with_suffix(".duckdb.wal"), anchor_path(paths)):
        if f.exists():
            os.chmod(f, stat.S_IWRITE | stat.S_IREAD)
            f.unlink()


def load_truth(con, landing: Path) -> int:
    """truth.injected_problems: the answer key. Read only by marts.detection_scorecard and tests (DESIGN 3.2)."""
    df = read_landing(landing / "injected_problems.csv", expected=TRUTH_COLS)
    df = df.reindex(columns=TRUTH_COLS) if not df.empty else pd.DataFrame(columns=TRUTH_COLS, dtype=str)
    con.register("_truth", df.astype(str) if not df.empty else df)
    con.execute(f"insert into truth.injected_problems select {', '.join(TRUTH_COLS)} from _truth")
    con.unregister("_truth")
    return len(df)


def check_seed(seed) -> int:
    """numpy needs a non-negative integer seed. Raises ValueError (before anything is deleted)."""
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise ValueError(f"seed must be a non-negative integer, got {seed!r}")
    return seed


def integrity_step(con, paths: Paths, truth: pd.DataFrame, tamper: bool = True) -> None:
    """Step 7, in GXP's order. Shared with tests/qa/qa_helpers.staged_build so the two cannot drift apart.
    Planted fraud runs after all audited writes (DESIGN 4): INJ-7 edits an audit row, INJ-11 a base row."""
    if tamper:
        from generator.tamper import tamper_audit_row, tamper_base_row
        for event_id in truth.loc[truth.inj_type == "INJ-7", "affected_key"]:
            tamper_audit_row(con, event_id)
        for event_id in truth.loc[truth.inj_type == "INJ-11", "affected_key"]:
            tamper_base_row(con, event_id)
    write_chain_verify(con, verify_chain(con))
    reconcile_records(con)   # base rows vs their audit rows (GXP, BUG-005)
    rehash_raw_files(con, paths.raw)
    write_chain_anchor(con, anchor_path(paths))   # write-once external anchor (GXP, BUG-004)


def build(root: Path, seed: int = 42, inject: bool = True, run_tamper: bool = True,
          optional_problems: bool = False, quiet: bool = False) -> Paths:
    """Steps 1-8 of DESIGN section 1 plus dbt build, into `root`/data. Returns the paths used."""
    say = (lambda *a: None) if quiet else print
    check_seed(seed)          # BUG-007: validate everything BEFORE deleting the previous run
    rules = load_rules()
    paths = default_paths(root)
    _clean(paths)
    paths.db.parent.mkdir(parents=True, exist_ok=True)

    say("1/8 generate synthetic study ...")
    gen = write(generate(seed, inject=inject, optional_problems=optional_problems), paths.landing)
    con = duckdb.connect(str(paths.db))
    try:
        create_schema(con)
        say("2/8 load mini-LIMS (audited) ...")
        lims = load_lims(con, paths.landing)
        assert all(lims[k] == gen[k] for k in lims), f"LIMS rows do not tie out: {lims} vs {gen}"
        say("3/8 ingest plates (read-only raw copies, SHA-256, plate map, ID_MISMATCH) ...")
        ingest_plates(con, paths.landing, paths.raw, rules)
        say("4/8 4PL fit per plate ...")
        fit_all(con, rules)
        say("5/8 QC rules + plate accept/reject ...")
        run_qc(con, rules)
        say("6/8 reportable run per sample ...")
        select_reportable(con)
        n_truth = load_truth(con, paths.landing)
        truth = con.execute("select * from truth.injected_problems").df()
        say("7/8 integrity: tamper (INJ-7, INJ-11), verify chain, reconcile records, re-hash raw files, anchor ...")
        integrity_step(con, paths, truth, tamper=inject and run_tamper)
        assert n_truth == gen["injected_problems"]
    finally:
        con.close()
    say("8/8 dbt build (staging, integrity, core, marts + tests) ...")
    LAST_DBT.clear()
    LAST_DBT.update(run_dbt(paths.db, dbt_vars(rules)))
    return paths


def run_dbt(db: Path, vars: dict) -> dict:
    """`dbt build` against `db` with the config vars. Target and log folders sit next to the DB, so parallel builds
    (main run and test fixtures) never share dbt/target. PYTHONPATH=ROOT lets mart_immunogenicity.py import
    pipeline.stats (DESIGN R4)."""
    db = Path(db)
    target, logs = db.parent / "dbt_target", db.parent / "dbt_logs"
    env = {**os.environ, "VAP_DB_PATH": str(db),
           "PYTHONPATH": os.pathsep.join([str(ROOT)] + ([os.environ["PYTHONPATH"]] if os.environ.get("PYTHONPATH")
                                                        else []))}
    dbt = Path(sys.executable).with_name("dbt.exe" if os.name == "nt" else "dbt")
    cmd = [str(dbt), "build", "--project-dir", str(ROOT / "dbt"), "--profiles-dir", str(ROOT / "dbt"),
           "--target-path", str(target), "--log-path", str(logs), "--vars", json.dumps(vars)]
    proc = subprocess.run(cmd, env=env, cwd=ROOT, capture_output=True, text=True)
    res_file = target / "run_results.json"
    if proc.returncode != 0 or not res_file.exists():
        print(proc.stdout[-6000:], proc.stderr[-2000:])
        raise RuntimeError("dbt build failed")
    res = json.loads(res_file.read_text())
    statuses = [r["status"] for r in res["results"]]
    return {"nodes": len(statuses), "passed": sum(s in ("success", "pass") for s in statuses),
            "warn": statuses.count("warn"), "failed": sum(s in ("error", "fail") for s in statuses),
            "models": sum(r["unique_id"].startswith("model.") for r in res["results"]),
            "tests": sum(r["unique_id"].startswith("test.") for r in res["results"])}


def run_pytest() -> dict:
    proc = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"], cwd=ROOT,
                          capture_output=True, text=True)
    tail = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""
    counts = {k: int(m.group(1)) if (m := re.search(rf"(\d+) {k}", tail)) else 0
              for k in ("passed", "failed", "skipped", "error")}
    print("pytest:", tail)
    return {**counts, "summary": tail, "date": time.strftime("%Y-%m-%d")}


def summarize(con) -> dict:
    """Headline numbers for docs/results.json and the README block (deterministic for a given seed)."""
    q = lambda sql: con.execute(sql).fetchone()[0]  # noqa: E731
    out = {
        "samples": q("select count(*) from lims.samples"),
        "plates": q("select count(*) from assay.plate_status"),
        "plates_rejected": q("select count(*) from assay.plate_status where status = 'REJECTED'"),
        "reportable": q("select count(*) from core.fct_reportable_result"),
        "missing": q("select count(*) from core.missing_results"),
        "reassay_rows": q("select count(*) from core.reassay_list"),
        "qc_flags_by_rule": dict(con.execute(
            "select rule_id, count(*) from assay.qc_flags group by 1 order by 1").fetchall()),
        "chain_ok": bool(q("select ok from audit.chain_verify order by verified_at desc limit 1")),
        "injected_problems": q("select count(distinct problem_id) from truth.injected_problems"),
    }
    tables = {r[0] for r in con.execute(
        "select table_schema || '.' || table_name from information_schema.tables").fetchall()}
    if "marts.detection_scorecard" in tables:
        out["scorecard"] = con.execute(
            "select * from marts.detection_scorecard order by problem_id, affected_key").df().to_dict("records")
        out["detected"] = q("select count(*) from (select problem_id from marts.detection_scorecard "
                            "group by 1 having bool_and(detected))")
    if "marts.scorecard_summary" in tables:
        out["scorecard_summary"] = con.execute("select * from marts.scorecard_summary").df().to_dict("records")[0]
        out["headline"] = out["scorecard_summary"]["headline"]
    if "marts.scorecard_false_positives" in tables:
        out["false_positives"] = con.execute("select * from marts.scorecard_false_positives").df() \
            .to_dict("records")[0]
    if "marts.mart_immunogenicity" in tables:
        out["immunogenicity"] = con.execute(
            "select * from marts.mart_immunogenicity order by group_name, visit").df().round(4).to_dict("records")
    return out


def write_readme_results(r: dict) -> None:
    """Rewrite the README block between the results markers (the README itself is owned by OPS)."""
    readme = ROOT / "README.md"
    if not readme.exists():
        return
    text = readme.read_text(encoding="utf-8")
    if "<!-- results:start -->" not in text:
        return
    s, t, d = r["summary"], r.get("tests"), r["dbt"]
    lines = ["| Result | Value |", "|---|---|",
             f"| Samples / plates (rejected) | **{s['samples']} / {s['plates']} ({s['plates_rejected']})** |",
             f"| Reportable / missing results | **{s['reportable']} / {s['missing']}** |"]
    if "headline" in s:
        lines.append(f"| Planted problems detected | **{s['headline']}** |")
    if "false_positives" in s:
        fp = s["false_positives"].get("fp_pct")
        fp_txt = f"{int(fp * 1000) / 1000:.3f}" if isinstance(fp, (int, float)) else fp   # truncated, never rounded up
        lines.append(f"| Unexplained sample-flag rate | **{fp_txt}%** |")
    lines.append(f"| Audit hash chain | **{'OK' if s['chain_ok'] else 'BROKEN (INJ-7 caught)'}** |")
    lines.append(f"| dbt build | **{d['passed']} of {d['nodes']} passed**, {d['failed']} failed |")
    if t:
        lines.append(f"| pytest | **{t['passed']} passed**, {t['failed']} failed ({t['date']}) |")
    note = (f"\nNumbers from `python -m pipeline.run --seed {r['seed']}`, stored in "
            "[docs/results.json](docs/results.json). Synthetic data only.\n")
    new = re.sub(r"<!-- results:start -->.*<!-- results:end -->",
                 lambda _: "<!-- results:start -->\n" + "\n".join(lines) + f"\n{note}<!-- results:end -->",
                 text, flags=re.S)
    readme.write_text(new, encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--test", action="store_true", help="also run pytest and record the counts")
    ap.add_argument("--optional-problems", action="store_true", help="also plant INJ-9 and INJ-10")
    a = ap.parse_args()
    try:
        check_seed(a.seed)
    except ValueError as e:
        ap.error(str(e))      # one-line message, exit code 2, data/ untouched
    t0 = time.perf_counter()
    paths = build(ROOT, seed=a.seed, inject=True, optional_problems=a.optional_problems)
    rules = load_rules()
    dbt = dict(LAST_DBT)
    with duckdb.connect(str(paths.db), read_only=True) as con:
        summary = summarize(con)
        exports, charts = {}, []
        try:
            from pipeline.export import export_marts
            exports = export_marts(con, paths.marts)
        except ImportError:
            print("export skipped: pipeline.export not delivered yet (LIA-06)")
        try:
            from pipeline.charts import render_charts
            charts = [Path(p).relative_to(ROOT).as_posix() for p in render_charts(con, paths.img)]
        except ImportError:
            print("charts skipped: pipeline.charts not delivered yet (LIA-06)")
    old = json.loads(RESULTS.read_text()) if RESULTS.exists() else {}
    tests = run_pytest() if a.test else old.get("tests")
    results = {"seed": a.seed, "rule_version": rules["version"], "summary": summary, "dbt": dbt,
               "exports": exports, "charts": charts, "tests": tests}
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    RESULTS.write_text(json.dumps(results, indent=2, default=str) + "\n")
    write_readme_results(results)
    print(json.dumps({k: v for k, v in summary.items() if k not in ("scorecard", "immunogenicity")}, default=str))
    print(f"dbt: {dbt}; tests: {tests and tests['summary']}; done in {time.perf_counter() - t0:.1f} s")
    if tests and (tests["failed"] or tests["error"]):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
