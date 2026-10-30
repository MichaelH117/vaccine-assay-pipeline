"""QA edge tests: malformed / truncated / odd plate-reader CSVs (AC-4.1). Pure parser tests, no build.

Rule under test: a bad file raises PlateFormatError (which ingest logs and skips). It must never raise anything else,
and it must never accept OD values the pipeline cannot use. xfail(strict) = a logged bug in docs/team/BUGS.md.
"""

from __future__ import annotations

import pytest

from pipeline.ingest import PlateFormatError, parse_plate_csv

ROWS = "ABCDEFGH"
HEADER = "," + ",".join(str(c) for c in range(1, 13))


def good_text() -> str:
    lines = [HEADER] + [r + "," + ",".join(f"{0.1 + 0.01 * (i * 12 + c):.3f}" for c in range(12))
                        for i, r in enumerate(ROWS)]
    return "\n".join(lines) + "\n"


def _write(tmp_path, text: str, name="P.csv", encoding="utf-8"):
    p = tmp_path / name
    p.write_text(text, encoding=encoding)
    return p


def _cell(text: str, value: str, row: int = 1, col: int = 1) -> str:
    lines = text.splitlines()
    cells = lines[row].split(",")
    cells[col] = value
    lines[row] = ",".join(cells)
    return "\n".join(lines) + "\n"


def test_good_file_gives_96_rows(tmp_path):
    df = parse_plate_csv(_write(tmp_path, good_text()), "P")
    assert len(df) == 96 and df.well.is_unique and df.od.notna().all()


@pytest.mark.parametrize("name, text", [
    ("empty", lambda t: ""),
    ("header_only", lambda t: HEADER + "\n"),
    ("truncated_mid_row", lambda t: t[: len(t) // 2]),
    ("seven_rows", lambda t: "\n".join(t.splitlines()[:8]) + "\n"),
    ("extra_column", lambda t: "\n".join(line + ",0.1" for line in t.splitlines()) + "\n"),
    ("semicolon_delimited", lambda t: t.replace(",", ";")),
    ("binary_garbage", lambda t: "\x00\x01\x02garbage"),
    ("duplicate_row_label", lambda t: "\n".join(t.splitlines()[:8] + [t.splitlines()[7]]) + "\n"),
    ("lowercase_row_labels", lambda t: "\n".join([HEADER] + [ln[0].lower() + ln[1:] for ln in t.splitlines()[1:]])),
    ("blank_cell", lambda t: _cell(t, "")),
    ("text_cell", lambda t: _cell(t, "OVER")),
    ("nan_cell", lambda t: _cell(t, "nan")),
    ("comma_decimal", lambda t: _cell(t, '"2,792"')),
])
def test_malformed_file_rejected_cleanly(tmp_path, name, text):
    with pytest.raises(PlateFormatError):
        parse_plate_csv(_write(tmp_path, text(good_text())), "P")


def test_utf16_file_rejected_cleanly(tmp_path):
    with pytest.raises(PlateFormatError):
        parse_plate_csv(_write(tmp_path, good_text(), encoding="utf-16"), "P")


@pytest.mark.parametrize("name, text", [
    ("utf8_bom", None), ("crlf", lambda t: t.replace("\n", "\r\n")), ("trailing_blank_lines", lambda t: t + "\n\n"),
    ("quoted_numbers", lambda t: _cell(t, '"0.111"')),
])
def test_harmless_variants_accepted(tmp_path, name, text):
    if text is None:
        p = _write(tmp_path, good_text(), encoding="utf-8-sig")
    else:
        p = _write(tmp_path, text(good_text()))
    assert len(parse_plate_csv(p, "P")) == 96


@pytest.mark.parametrize("value", ["inf", "-inf", "Infinity"])
def test_infinite_od_rejected(tmp_path, value):
    with pytest.raises(PlateFormatError):
        parse_plate_csv(_write(tmp_path, _cell(good_text(), value)), "P")


@pytest.mark.parametrize("value", ["-5.0", "1e300"])
def test_implausible_od_rejected(tmp_path, value):
    with pytest.raises(PlateFormatError):
        parse_plate_csv(_write(tmp_path, _cell(good_text(), value)), "P")


@pytest.mark.parametrize("which", ["lowercase", "duplicate"])
def test_label_error_message_names_the_labels(tmp_path, which):
    lines = good_text().splitlines()
    if which == "lowercase":
        bad = "\n".join([HEADER] + [ln[0].lower() + ln[1:] for ln in lines[1:]])
    else:
        bad = "\n".join(lines[:8] + [lines[7]])
    with pytest.raises(PlateFormatError) as e:
        parse_plate_csv(_write(tmp_path, bad), "P")
    assert "8x12" not in str(e.value) or "label" in str(e.value).lower()
