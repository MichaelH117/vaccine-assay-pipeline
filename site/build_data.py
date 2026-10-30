"""Precompute the small JSON files the Quarto site reads (design-lead seat).

Run from the repo root AFTER `python -m pipeline.run`:

    .venv\\Scripts\\python site\\build_data.py

Every number comes from the pipeline's own outputs: docs/results.json, data/marts/*.csv and the read-only
DuckDB warehouse. No metric is re-derived here except where noted, and each of those is checked against the mart
(the script stops with an AssertionError if it disagrees). Output: site/data/*.json (a few hundred KB in total), so
the browser never needs DuckDB-WASM. All data is SYNTHETIC.
"""
from __future__ import annotations

import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline.audit import AUDIT_COLUMNS, compute_row_hash  # noqa: E402  (same code the pipeline verifies with)
from pipeline.stats import is_seroresponder  # noqa: E402

OUT = ROOT / "site" / "data"
OUT.mkdir(parents=True, exist_ok=True)
DB = ROOT / "data" / "warehouse" / "vaccine_assay.duckdb"
MARTS = ROOT / "data" / "marts"


def clean(v):
    if isinstance(v, float) and v != v:
        return None
    if isinstance(v, (pd.Timestamp, dt.datetime)):
        return pd.Timestamp(v).isoformat()
    if hasattr(v, "item"):
        return clean(v.item())
    if v is pd.NA:
        return None
    return v


def records(df: pd.DataFrame) -> list[dict]:
    return [{k: clean(v) for k, v in r.items()} for r in df.to_dict("records")]


def dump(name: str, obj) -> None:
    (OUT / name).write_text(json.dumps(obj, separators=(",", ":"), ensure_ascii=False, allow_nan=False), encoding="utf-8")
    print(f"  wrote site/data/{name} ({(OUT / name).stat().st_size:,} bytes)")


results = json.loads((ROOT / "docs" / "results.json").read_text(encoding="utf-8"))
con = duckdb.connect(str(DB), read_only=True)
cfg_lloq = 45.72  # config/qc_rules.yaml assay.assay_lloq_au_ml (checked below against the mart counts)
cfg_fold = 4.0    # config/qc_rules.yaml immunogenicity.seroresponse_fold

# ---------------------------------------------------------------- meta (status badge)
verify = records(con.execute("SELECT * FROM audit.chain_verify").df())[0]
anchor = json.loads((ROOT / "data" / "warehouse" / "audit_anchor.json").read_text(encoding="utf-8"))
try:
    sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True,
                         check=True).stdout.strip()
except Exception:  # noqa: BLE001
    sha = "unknown"
s = results["summary"]
meta = {
    "run_at_utc": anchor["written_at_utc"][:19],
    "seed": results["seed"],
    "rule_version": results["rule_version"],
    "dbt": results["dbt"],
    "tests": results["tests"],
    "git_sha": sha,
    "headline": s["headline"],
    "samples": s["samples"], "plates": s["plates"], "plates_rejected": s["plates_rejected"],
    "reportable": s["reportable"], "missing": s["missing"], "reassay_rows": s["reassay_rows"],
    "qc_flags_by_rule": s["qc_flags_by_rule"],
    "false_positives": s["false_positives"],
    "scorecard_summary": s["scorecard_summary"],
    "chain_ok": s["chain_ok"],
    "chain_verify": verify,
    "audit_rows_total": anchor["head_seq"],
}
dump("meta.json", meta)

# ---------------------------------------------------------------- immunogenicity + lab KPIs
imm = pd.read_csv(MARTS / "mart_immunogenicity.csv")
dump("immunogenicity.json", records(imm))
dump("lab_kpis.json", records(pd.read_csv(MARTS / "mart_lab_kpis.csv")))

# ---------------------------------------------------------------- 1 dot = 1 volunteer
rr = con.execute(
    "SELECT subject_id, group_name, visit, analysis_value_au_ml FROM core.fct_reportable_result"
).df()
subs = con.execute("SELECT subject_id, group_name FROM lims.subjects ORDER BY subject_id").df() \
    if "group_name" in con.execute("SELECT * FROM lims.subjects LIMIT 0").df().columns else None
if subs is None:
    subs = rr[["subject_id", "group_name"]].drop_duplicates().sort_values("subject_id")
wide = rr.pivot_table(index="subject_id", columns="visit", values="analysis_value_au_ml", aggfunc="first")
dots = []
for visit in ["D29", "D57"]:
    for _, srow in subs.iterrows():
        sid, grp = srow["subject_id"], srow["group_name"]
        base = wide.at[sid, "D1"] if sid in wide.index and "D1" in wide.columns else None
        post = wide.at[sid, visit] if sid in wide.index and visit in wide.columns else None
        has = base is not None and post is not None and pd.notna(base) and pd.notna(post)
        resp = bool(is_seroresponder([base], [post], cfg_lloq, cfg_fold)[0]) if has else None
        dots.append({"subject_id": sid, "group": grp, "visit": visit,
                     "base": clean(base) if has else None, "post": clean(post) if has else None,
                     "fold": round(float(post) / float(base), 2) if has else None,
                     "status": "no result" if not has else ("responded" if resp else "did not respond")})
dd = pd.DataFrame(dots)
for _, m in imm.dropna(subset=["sero_total"]).iterrows():
    sub = dd[(dd.group == m.group_name) & (dd.visit == m.visit) & (dd.status != "no result")]
    assert len(sub) == m.sero_total, (m.group_name, m.visit, len(sub), m.sero_total)
    assert (sub.status == "responded").sum() == m.sero_n, (m.group_name, m.visit)
print("  per-volunteer seroresponse matches mart_immunogenicity sero_n / sero_total for every group x visit")
dump("volunteers.json", dots)

# ---------------------------------------------------------------- follow one tube (INJ-7 and INJ-11)
truth = con.execute("SELECT inj_type, affected_key FROM truth.injected_problems").df()


def tube(event_id: str, inj: str) -> dict:
    sid = con.execute("SELECT sample_id FROM lims.custody_events WHERE event_id = ?", [event_id]).fetchone()[0]
    ev = con.execute("SELECT * FROM lims.custody_events WHERE sample_id = ? ORDER BY performed_at, event_id",
                     [sid]).df()
    keys = list(ev.event_id)
    aud = con.execute(
        f"SELECT {', '.join(AUDIT_COLUMNS)} FROM audit.audit_log WHERE table_name = 'lims.custody_events' "
        f"AND record_key IN ({', '.join('?' * len(keys))}) AND action = 'INSERT' ORDER BY audit_seq", keys
    ).df()
    prevrow = con.execute("SELECT row_hash FROM audit.audit_log WHERE audit_seq = ?",
                          [int(aud.audit_seq.min()) - 1]).fetchone()
    steps = []
    for _, a in aud.iterrows():
        row = {c: a[c] for c in AUDIT_COLUMNS}
        row = {k: (None if (not isinstance(v, str) and pd.isna(v)) else v) for k, v in row.items()}
        live = ev[ev.event_id == row["record_key"]].iloc[0]
        stored_rec = json.loads(row["new_value"])
        recomputed = compute_row_hash(row["prev_hash"], row)
        step = {
            "audit_seq": int(row["audit_seq"]), "event_id": row["record_key"], "step": live["step"],
            "location": live["location"], "plate_id": clean(live["plate_id"]), "well": clean(live["well"]),
            "live_performed_by": live["performed_by"], "live_performed_at": clean(live["performed_at"]),
            "audit_performed_by": stored_rec.get("performed_by"),
            "audit_performed_at": stored_rec.get("performed_at"),
            "prev_hash": row["prev_hash"], "row_hash": row["row_hash"], "recomputed_hash": recomputed,
            "seal_ok": recomputed == row["row_hash"],
            "record_matches_audit": (stored_rec.get("performed_by") == live["performed_by"]
                                     and stored_rec.get("performed_at") == pd.Timestamp(
                                         live["performed_at"]).isoformat()),
        }
        if inj == "INJ-7" and row["record_key"] == event_id:
            # Undo generator/tamper.py's documented edit (performed_at moved back one day) and prove the
            # reconstruction is the original: its recomputed hash must equal the hash stored at load time.
            orig = dict(stored_rec)
            orig["performed_at"] = (dt.datetime.fromisoformat(orig["performed_at"]) + dt.timedelta(days=1)).isoformat()
            orig_json = json.dumps(orig, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            orig_hash = compute_row_hash(row["prev_hash"], {**row, "new_value": orig_json})
            assert orig_hash == row["row_hash"], "reconstructed pre-tamper row does not match the stored seal"
            step["before_tamper"] = {"performed_at": orig["performed_at"], "recomputed_hash": orig_hash,
                                     "seal_ok": True}
        steps.append(step)
    # links: each row's prev_hash must equal the row before it (only checkable inside a contiguous run)
    for i, st in enumerate(steps):
        before = steps[i - 1]["row_hash"] if i else (prevrow[0] if prevrow else None)
        st["link_ok"] = st["prev_hash"] == before
    return {"inj_type": inj, "event_id": event_id, "sample_id": sid, "steps": steps}


e7 = truth.loc[truth.inj_type == "INJ-7", "affected_key"].iloc[0]
e11 = truth.loc[truth.inj_type == "INJ-11", "affected_key"].iloc[0]
recon = records(con.execute("SELECT * FROM audit.record_reconciliation WHERE issue <> 'RUN'").df())
t7, t11 = tube(e7, "INJ-7"), tube(e11, "INJ-11")
assert any(not st["seal_ok"] for st in t7["steps"]), "INJ-7 tube should have a broken seal"
assert all(st["seal_ok"] for st in t11["steps"]), "INJ-11 tube audit rows should all verify"
dump("tubes.json", {"tubes": [t7, t11], "chain_verify": verify, "record_reconciliation": recon,
                    "users": records(con.execute("SELECT user_id, display_name, role FROM lims.users").df())})

# ---------------------------------------------------------------- plates, wells, 4PL
qc = pd.read_csv(MARTS / "mart_plate_qc.csv").fillna({"reject_reasons": "", "repeat_of_plate_id": ""})
wells = con.execute("""
    SELECT w.plate_id, w.well, w.row_letter, w.col_num, w.od, m.well_type, m.level, m.sample_id, m.dilution
    FROM assay.well_reads w LEFT JOIN assay.plate_map m USING (plate_id, well)
    ORDER BY w.plate_id, w.row_letter, w.col_num""").df()
flags = con.execute("SELECT plate_id, sample_id, rule_id, blocking, message FROM assay.qc_flags").df()
std = con.execute("SELECT * FROM assay.std_recovery ORDER BY plate_id, level").df()
smp = con.execute("""SELECT plate_id, sample_id, dilution, mean_od, range_flag, conc_au_ml
                     FROM assay.sample_results ORDER BY plate_id, sample_id""").df()
fits = con.execute("SELECT * FROM assay.curve_fits ORDER BY plate_id").df()
dump("plates.json", {"plates": records(qc), "wells": records(wells), "flags": records(flags),
                     "standards": records(std), "samples": records(smp), "fits": records(fits)})

# ---------------------------------------------------------------- scorecard
sc = pd.read_csv(MARTS / "detection_scorecard.csv")
dump("scorecard.json", {"rows": records(sc),
                        "summary": records(pd.read_csv(MARTS / "scorecard_summary.csv"))[0],
                        "false_positives": records(pd.read_csv(MARTS / "scorecard_false_positives.csv"))[0],
                        "alcoa": records(pd.read_csv(MARTS / "alcoa_findings.csv"))})
con.close()

# ---------------------------------------------------------------- story numbers (site/_variables.yml)
# The overview's above-the-fold text uses Quarto {{< var >}} shortcodes so the headline numbers are in the static
# HTML (no JavaScript needed to read them). Headline decimals are truncated, never rounded up.
import math  # noqa: E402


def t1(x: float) -> str:
    return f"{math.floor(x * 10) / 10:.1f}"


def n0(x: float) -> str:
    return f"{math.floor(x):,}"


def immrow(g: str, v: str):
    r = imm[(imm.group_name == g) & (imm.visit == v)]
    assert len(r) == 1, (g, v)
    return r.iloc[0]


v29, p29, v57, p57 = immrow("Vaccine", "D29"), immrow("Placebo", "D29"), immrow("Vaccine", "D57"), immrow("Placebo", "D57")
kp = {r["kpi_id"]: r for r in records(pd.read_csv(MARTS / "mart_lab_kpis.csv"))}
ss, fp = s["scorecard_summary"], s["false_positives"]
story = {
    "vac_d29_n": int(v29.sero_n), "vac_d29_total": int(v29.sero_total), "vac_d29_pct": t1(v29.sero_pct),
    "vac_d29_lcl": t1(v29.sero_lcl), "vac_d29_ucl": t1(v29.sero_ucl),
    "pla_d29_n": int(p29.sero_n), "pla_d29_total": int(p29.sero_total), "pla_d29_ucl": t1(p29.sero_ucl),
    "vac_d29_gmt": n0(v29.gmt), "pla_d29_gmt": n0(p29.gmt), "gmr_d29": t1(v29.gmt / p29.gmt),
    "vac_d29_gmfr": t1(v29.gmfr), "vac_d57_gmfr": t1(v57.gmfr),
    "vac_d57_gmt": n0(v57.gmt), "pla_d57_gmt": n0(p57.gmt), "vac_d1_gmt": n0(immrow("Vaccine", "D1").gmt),
    "problems_detected": int(ss["problems_detected"]), "problems_planted": int(ss["problems_planted"]),
    "keys_detected": int(ss["keys_detected"]), "keys_planted": int(ss["keys_planted"]),
    "problem_types": int(ss["required_inj_types_planted"]),
    "plates": int(s["plates"]), "plates_rejected": int(s["plates_rejected"]),
    "plates_accepted": int(s["plates"]) - int(s["plates_rejected"]),
    "plates_false_reject": int(fp["plates_rejected_unexplained"]),
    "samples": int(s["samples"]), "samples_unexplained": int(fp["samples_with_unexplained_flag"]),
    "reportable": int(s["reportable"]), "missing": int(s["missing"]), "reassay": int(s["reassay_rows"]),
    "reassay_pct": t1(kp["REASSAY_RATE"]["value"]),
    "tat_median": t1(kp["TAT_MEDIAN_DAYS"]["value"]), "tat_p90": t1(kp["TAT_P90_DAYS"]["value"]),
    "chain_row": n0(verify["first_broken_seq"]), "audit_rows": n0(anchor["head_seq"]),
    "chain_rows_checked": n0(verify["rows_checked"]), "tamper_key": verify["broken_record_key"],
    "tamper_detected": "yes" if (not s["chain_ok"] and verify["first_broken_seq"]) else "no",
    "run_at": meta["run_at_utc"].replace("T", " ")[:16],
    "tests_passed": int(results["tests"]["passed"]), "dbt_passed": int(results["dbt"]["passed"]),
    "dbt_nodes": int(results["dbt"]["nodes"]),
}
# The story's verdict depends on these facts; stop the build if the data no longer supports "On track".
assert story["problems_detected"] == story["problems_planted"], "not every planted problem was caught"
assert story["plates_false_reject"] == 0, "a plate was rejected without a planted cause"
assert story["tamper_detected"] == "yes", "the planted tamper was not detected"
assert v29.sero_lcl > p29.sero_ucl, "vaccine and placebo response intervals overlap"
lines = ["# Written by site/build_data.py from docs/results.json and data/marts. Do not edit by hand.\n"]
lines += [f'{k}: "{v}"\n' for k, v in story.items()]
(ROOT / "site" / "_variables.yml").write_text("".join(lines), encoding="utf-8")
print(f"  wrote site/_variables.yml ({len(story)} story numbers; verdict checks passed)")
print("done")
