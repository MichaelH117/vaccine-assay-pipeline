"""Plate ingestion: parser, bad files, read-only raw copies, ID_MISMATCH (US-4, AC-3.5)."""

from __future__ import annotations

import os
import shutil

import duckdb
import pytest

from generator.generate import generate, write
from pipeline.config import load_rules
from pipeline.ingest import PlateFormatError, ingest_plates, make_writable, parse_plate_csv
from pipeline.lims_load import load_lims
from pipeline.schema import create_schema

GOOD = ",1,2,3,4,5,6,7,8,9,10,11,12\n" + "".join(
    f"{r}," + ",".join(f"{0.1 + i / 100:.3f}" for i in range(12)) + "\n" for r in "ABCDEFGH")


def test_good_file_gives_96_rows(tmp_path):
    p = tmp_path / "PLATE-001.csv"
    p.write_text(GOOD)
    df = parse_plate_csv(p, "PLATE-001")
    assert len(df) == 96
    assert list(df.columns) == ["plate_id", "well", "row_letter", "col_num", "od"]
    assert df.well.is_unique and set(df.row_letter) == set("ABCDEFGH") and set(df.col_num) == set(range(1, 13))
    assert df.set_index("well").loc["C5", "od"] == pytest.approx(0.14)


def test_7x12_file_is_rejected(tmp_path):
    p = tmp_path / "bad.csv"
    p.write_text("\n".join(GOOD.splitlines()[:-1]) + "\n")
    with pytest.raises(PlateFormatError, match="8x12"):
        parse_plate_csv(p, "X")


def test_non_numeric_file_is_rejected(tmp_path):
    p = tmp_path / "bad.csv"
    p.write_text(GOOD.replace("A,0.100", "A,OVER"))
    with pytest.raises(PlateFormatError, match="non-numeric"):
        parse_plate_csv(p, "X")


def test_empty_file_is_rejected(tmp_path):
    p = tmp_path / "empty.csv"
    p.write_text("")
    with pytest.raises(PlateFormatError):
        parse_plate_csv(p, "X")


@pytest.fixture()
def landed(tmp_path):
    landing = tmp_path / "landing"
    write(generate(42), landing)
    con = duckdb.connect(":memory:")
    create_schema(con)
    load_lims(con, landing)
    yield con, landing, tmp_path / "raw"
    make_writable(tmp_path / "raw")
    con.close()


def test_bad_file_is_logged_and_run_continues(landed):
    con, landing, raw = landed
    f = landing / "plates" / "PLATE-008.csv"
    f.write_text("\n".join(f.read_text().splitlines()[:-1]) + "\n")
    out = ingest_plates(con, landing, raw, load_rules())
    assert out["rejected"] == 1 and out["parsed"] == out["files"] - 1
    err = con.execute("select file_name, error from assay.ingest_errors").fetchall()
    assert err[0][0] == "PLATE-008.csv" and "8x12" in err[0][1]
    # its plate map is still loaded, so QC can reject the plate and re-assay its samples (BUG-003)
    assert con.execute("select count(*) from assay.plate_map where plate_id = 'PLATE-008'").fetchone()[0] > 0


def test_stray_and_duplicate_files_are_logged_not_parsed(landed):  # BUG-006
    con, landing, raw = landed
    shutil.copy(landing / "plates" / "PLATE-002.csv", landing / "plates" / "PLATE-002 (1).csv")
    (landing / "plates" / "PLATE-099.csv").write_text(GOOD)
    out = ingest_plates(con, landing, raw, load_rules())
    err = dict(con.execute("select file_name, error from assay.ingest_errors").fetchall())
    assert set(err) == {"PLATE-002 (1).csv", "PLATE-099.csv"} and out["rejected"] == 2
    assert "duplicate upload" in err["PLATE-002 (1).csv"] and "PLATE-002.csv" in err["PLATE-002 (1).csv"]
    assert con.execute("select count(distinct plate_id) from assay.well_reads").fetchone()[0] == out["files"] - 2
    assert con.execute("select count(*) from lims.raw_files").fetchone()[0] == out["files"]   # upload on record


@pytest.mark.parametrize("value, match", [("inf", "infinite"), ("-5.0", "reader range"), ("9.9", "reader range")])
def test_non_finite_or_implausible_od_rejected(tmp_path, value, match):  # BUG-001, BUG-002
    p = tmp_path / "p.csv"
    p.write_text(GOOD.replace("A,0.100", f"A,{value}"))
    with pytest.raises(PlateFormatError, match=match):
        parse_plate_csv(p, "X")


def test_label_errors_name_the_labels(tmp_path):  # BUG-008
    p = tmp_path / "p.csv"
    p.write_text(GOOD.replace("\nA,", "\na,"))
    with pytest.raises(PlateFormatError, match="row labels must be A-H"):
        parse_plate_csv(p, "X")


def test_raw_copies_are_read_only_and_hashed(landed):  # AC-3.5
    con, landing, raw = landed
    ingest_plates(con, landing, raw, load_rules())
    files = sorted(raw.glob("*.csv"))
    assert files and all(not os.access(f, os.W_OK) for f in files)
    rows = con.execute("select file_name, sha256 from lims.raw_files order by 1").fetchall()
    import hashlib
    assert rows == [(f.name, hashlib.sha256(f.read_bytes()).hexdigest()) for f in files]
    # the landing originals are byte-identical to the raw copies (processing never changes raw files)
    assert all(f.read_bytes() == (landing / "plates" / f.name).read_bytes() for f in files)


def test_reingest_over_read_only_copies_works(landed):  # DESIGN R6
    con, landing, raw = landed
    ingest_plates(con, landing, raw, load_rules())
    make_writable(raw)
    shutil.rmtree(raw)
    assert not raw.exists()


def test_blank_correction(landed):  # AC-4.3
    con, landing, raw = landed
    ingest_plates(con, landing, raw, load_rules())
    bad = con.execute("""
        with b as (select w.plate_id, avg(od) m from assay.well_reads w join assay.plate_map p using (plate_id, well)
                   where well_type = 'BLANK' group by 1)
        select count(*) from assay.well_reads w join b using (plate_id)
        where abs(w.od_blank_corrected - (w.od - b.m)) > 1e-6""").fetchone()[0]
    assert bad == 0


def test_inj2_gives_exactly_two_id_mismatch_flags(landed):  # AC-4.4
    con, landing, raw = landed
    ingest_plates(con, landing, raw, load_rules())
    flags = con.execute("select sample_id, blocking, rule_version from assay.qc_flags "
                        "where rule_id = 'ID_MISMATCH'").fetchall()
    truth = generate(42).injected_problems
    assert {f[0] for f in flags} == set(truth.loc[truth.inj_type == "INJ-2", "affected_key"])
    assert len(flags) == 2 and all(f[1] for f in flags) and flags[0][2] == load_rules()["version"]


def test_every_insert_is_audited(landed):  # AC-3.1
    con, landing, raw = landed
    ingest_plates(con, landing, raw, load_rules())
    for t in ("lims.custody_events", "lims.raw_files", "assay.plate_map", "assay.well_reads"):
        n = con.execute(f"select count(*) from {t}").fetchone()[0]
        a = con.execute("select count(*) from audit.audit_log where table_name = ? and action = 'INSERT'",
                        [t]).fetchone()[0]
        assert n == a > 0, t


@pytest.mark.parametrize("csv, col", [("subjects.csv", "site_id"), ("custody_events.csv", "location"),
                                      ("users.csv", "role")])
def test_missing_landing_column_fails_loudly(tmp_path, csv, col):  # BUG-011
    import pandas as pd

    from pipeline.lims_load import LandingSchemaError
    landing = tmp_path / "landing"
    write(generate(42), landing)
    df = pd.read_csv(landing / csv, dtype=str, keep_default_na=False)
    df.drop(columns=[col]).to_csv(landing / csv, index=False, lineterminator="\n")
    con = duckdb.connect(":memory:")
    create_schema(con)
    with pytest.raises(LandingSchemaError, match=rf"{csv}.*missing \['{col}'\]"):
        load_lims(con, landing)
    con.close()


def test_missing_plate_map_column_fails_loudly(landed):  # BUG-011
    import pandas as pd

    from pipeline.lims_load import LandingSchemaError
    con, landing, raw = landed
    pm = pd.read_csv(landing / "plate_map.csv", dtype=str, keep_default_na=False)
    pm.drop(columns=["dilution"]).to_csv(landing / "plate_map.csv", index=False, lineterminator="\n")
    with pytest.raises(LandingSchemaError, match="dilution"):
        ingest_plates(con, landing, raw, load_rules())
