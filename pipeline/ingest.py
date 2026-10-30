"""Plate-reader ingestion (US-4, AC-3.5).

For each raw plate CSV: copy it to data/raw/ and make the copy read-only, store its SHA-256 in lims.raw_files, parse
the 8x12 grid into 96 well rows, join the plate map, blank-correct, and reconcile each sample well against the LIMS
`assayed` custody event for that plate and well (ID_MISMATCH, catches INJ-2). A malformed file, or a file whose name
is not a planned plate in lims.plate_runs (a stray or duplicate upload), is logged to assay.ingest_errors and not
parsed; the run continues. Every file is still copied and hashed, so the upload itself stays on record.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import os
import shutil
import stat
from pathlib import Path

import numpy as np
import pandas as pd

from pipeline.config import load_rules
from pipeline.lims_load import read_landing, table_columns
from pipeline.schema import write_table

ROWS = list("ABCDEFGH")
COLS = [str(c) for c in range(1, 13)]


class PlateFormatError(ValueError):
    """A raw plate file is not an 8x12 grid of numeric OD values with A-H / 1-12 labels."""


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _od_limits() -> tuple[float, float]:
    p = load_rules()["plate"]
    return float(p["min_raw_od"]), float(p["max_raw_od"])


def parse_plate_csv(path: Path, plate_id: str, od_limits: tuple[float, float] | None = None) -> pd.DataFrame:
    """Raw reader file (header `,1,...,12`, rows A-H) -> 96 rows: plate_id, well, row_letter, col_num, od.
    Raises PlateFormatError for any other shape or labels, a non-numeric / missing / non-finite OD, or an OD outside
    the plausible reader range (`plate.min_raw_od` .. `plate.max_raw_od` in the config; a corrupt export)."""
    name = Path(path).name
    try:
        raw = pd.read_csv(path, dtype=str, keep_default_na=False, header=0, index_col=0)
    except Exception as e:   # empty file, ragged rows, bad encoding
        raise PlateFormatError(f"{name}: unreadable ({type(e).__name__}: {e})") from e
    raw.index = raw.index.astype(str).str.strip()
    raw.columns = [str(c).strip() for c in raw.columns]
    if raw.shape != (8, 12):
        raise PlateFormatError(f"{name}: expected an 8x12 grid, got {raw.shape[0]}x{raw.shape[1]}")
    if list(raw.index) != ROWS:
        raise PlateFormatError(f"{name}: row labels must be A-H in order, got {','.join(raw.index)}")
    if list(raw.columns) != COLS:
        raise PlateFormatError(f"{name}: column labels must be 1-12 in order, got {','.join(raw.columns)}")
    od = raw.apply(lambda s: pd.to_numeric(s.str.strip(), errors="coerce"))
    bad = [f"{r}{c}" for r in ROWS for c in COLS if not np.isfinite(od.loc[r, c])]
    if bad:
        raise PlateFormatError(f"{name}: non-numeric, missing or infinite OD in {len(bad)} well(s), e.g. {bad[:3]}")
    lo, hi = od_limits or _od_limits()
    out = [f"{r}{c}={od.loc[r, c]:g}" for r in ROWS for c in COLS if not lo <= od.loc[r, c] <= hi]
    if out:
        raise PlateFormatError(f"{name}: OD outside the plausible reader range {lo:g}-{hi:g} in {len(out)} well(s), "
                               f"e.g. {out[:3]}")
    long = od.stack().rename("od").reset_index()
    long.columns = ["row_letter", "col_num", "od"]
    long["col_num"] = long["col_num"].astype(int)
    long["well"] = long["row_letter"] + long["col_num"].astype(str)
    long.insert(0, "plate_id", plate_id)
    return long.sort_values(["col_num", "row_letter"])[["plate_id", "well", "row_letter", "col_num", "od"]] \
        .reset_index(drop=True)


def make_writable(folder: Path) -> None:
    """Undo the read-only flag on every file under `folder`, so a re-run can replace them (DESIGN R6)."""
    for p in Path(folder).rglob("*"):
        if p.is_file():
            os.chmod(p, stat.S_IWRITE | stat.S_IREAD)


def _copy_read_only(src: Path, raw: Path) -> Path:
    raw.mkdir(parents=True, exist_ok=True)
    dst = raw / src.name
    if dst.exists():
        os.chmod(dst, stat.S_IWRITE | stat.S_IREAD)
    shutil.copyfile(src, dst)
    os.chmod(dst, stat.S_IREAD)
    return dst


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.UTC).replace(tzinfo=None)


def id_mismatches(plate_map: pd.DataFrame, custody: pd.DataFrame) -> pd.DataFrame:
    """Well-level reconciliation (AC-4.4). Compares each plate-map sample pair (first well) with the LIMS `assayed`
    event for the same plate and well. Returns plate_id, sample_id, well, message for each mismatch:
    a different sample in the LIMS at that well, or no LIMS `assayed` record for it."""
    s = plate_map[plate_map.well_type == "SAMPLE"].copy()
    s["col_num"] = s.well.str[1:].astype(int)
    s["row_letter"] = s.well.str[0]
    first = (s.sort_values(["plate_id", "sample_id", "col_num", "row_letter"])
             .groupby(["plate_id", "sample_id"], as_index=False).first()[["plate_id", "sample_id", "well"]])
    assayed = custody.loc[custody.step == "assayed", ["plate_id", "well", "sample_id"]] \
        .rename(columns={"sample_id": "lims_sample_id"})
    m = first.merge(assayed, on=["plate_id", "well"], how="left")
    bad = m[m.lims_sample_id.isna() | (m.lims_sample_id != m.sample_id)].copy()
    bad["message"] = np.where(
        bad.lims_sample_id.isna(),
        "plate map has " + bad.sample_id + " at " + bad.well + " but the LIMS has no assayed record there",
        "plate map has " + bad.sample_id + " at " + bad.well + " but the LIMS assayed record says "
        + bad.lims_sample_id.fillna(""))
    # LIMS says a sample was assayed on this plate, but the plate map does not have it anywhere on the plate.
    on_map = set(zip(first.plate_id, first.sample_id, strict=True))
    orphan = assayed[[(p, x) not in on_map for p, x in zip(assayed.plate_id, assayed.lims_sample_id, strict=True)]]
    orphan = orphan[orphan.plate_id.isin(set(first.plate_id))]
    extra = pd.DataFrame(dict(plate_id=orphan.plate_id, sample_id=orphan.lims_sample_id, well=orphan.well,
                              message="LIMS assayed record for " + orphan.lims_sample_id + " at " + orphan.well
                              + " is not in the plate map"))
    out = pd.concat([bad[["plate_id", "sample_id", "well", "message"]], extra], ignore_index=True)
    return out.drop_duplicates(["plate_id", "sample_id"]).sort_values(["plate_id", "sample_id"]).reset_index(drop=True)


def ingest_plates(con, landing: Path, raw: Path, rules: dict) -> dict:
    """Copy, hash, parse, join and reconcile every plate in landing/plates/. Returns counts."""
    landing, raw = Path(landing), Path(raw)
    plate_map = read_landing(landing / "plate_map.csv", int_cols=["level", "dilution"],
                             expected=table_columns(con, "assay.plate_map"))
    plate_map["nominal_conc"] = pd.to_numeric(plate_map["nominal_conc"])
    files = sorted((landing / "plates").glob("*.csv"))
    planned = {p for (p,) in con.execute("select plate_id from lims.plate_runs").fetchall()}
    limits = (float(rules["plate"]["min_raw_od"]), float(rules["plate"]["max_raw_od"]))

    raw_rows, reads, errors = [], [], []
    sha_of = {}
    for src in files:
        dst = _copy_read_only(src, raw)
        sha = sha256_file(dst)
        sha_of[dst.name] = sha
        raw_rows.append(dict(file_name=dst.name, plate_id=src.stem if src.stem in planned else None,
                             raw_path=dst.as_posix(), sha256=sha, ingested_at=_utc_now()))
    for row in raw_rows:
        name, plate_id = row["file_name"], row["plate_id"]
        if plate_id is None:   # BUG-006: never silently ignore a stray file
            twins = sorted(n for n, h in sha_of.items() if h == row["sha256"] and n != name)
            why = f"; same SHA-256 as {', '.join(twins)} (duplicate upload)" if twins else ""
            errors.append(dict(file_name=name, error=f"{name}: file name is not a planned plate in lims.plate_runs"
                                                     f"{why}; not processed", logged_at=_utc_now()))
            continue
        try:
            reads.append(parse_plate_csv(raw / name, plate_id, limits))
        except PlateFormatError as e:
            errors.append(dict(file_name=name, error=str(e), logged_at=_utc_now()))
    write_table(con, "lims.raw_files", pd.DataFrame(raw_rows), ["file_name"], "raw plate file ingested (SHA-256)")
    if errors:   # not audited: holds no result (DESIGN 3.2)
        con.register("_err", pd.DataFrame(errors))
        con.execute("insert into assay.ingest_errors select file_name, error, logged_at from _err")
        con.unregister("_err")

    # The map of every planned plate is loaded, parsed or not, so samples on an unreadable plate stay traceable
    # (BUG-003: QC rejects that plate with INGEST_ERROR and its samples go on the re-assay list).
    pm = plate_map[plate_map.plate_id.isin(planned)]
    write_table(con, "assay.plate_map", pm, ["plate_id", "well"], "plate map from landing/plate_map.csv")
    n_reads = 0
    if reads:
        wr = pd.concat(reads, ignore_index=True)
        blanks = wr.merge(pm[pm.well_type == "BLANK"][["plate_id", "well"]], on=["plate_id", "well"])
        blank_mean = blanks.groupby("plate_id")["od"].mean()
        wr["od_blank_corrected"] = (wr["od"] - wr["plate_id"].map(blank_mean)).round(6)
        n_reads = write_table(con, "assay.well_reads", wr, ["plate_id", "well"], "plate reader OD parsed")

    custody = con.execute("select sample_id, step, plate_id, well from lims.custody_events").df()
    mm = id_mismatches(pm, custody)
    flags = pd.DataFrame(dict(
        flag_id="ID_MISMATCH:" + mm.plate_id + ":" + mm.sample_id, level="SAMPLE", plate_id=mm.plate_id,
        sample_id=mm.sample_id, rule_id="ID_MISMATCH", rule_version=rules["version"], measured_value=np.nan,
        threshold="plate map sample = LIMS assayed sample at plate+well", blocking=True, message=mm.message))
    write_table(con, "assay.qc_flags", flags, ["flag_id"], "QC rule ID_MISMATCH (plate map vs LIMS)")
    return {"files": len(files), "parsed": len(reads), "rejected": len(errors), "well_reads": n_reads,
            "id_mismatch": len(flags)}
