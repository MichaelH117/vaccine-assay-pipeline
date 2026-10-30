"""Repeat-run check, part 2 (FLAW_HUNT FH-01). Usage: python tools/compare_duckdb_runs.py A.duckdb B.duckdb

Compares every base table of two DuckDB files from two runs with the same seed. A table is "identical", or "differs
only in excluded run-clock columns" (timestamps, hashes and audit payloads that embed a timestamp), or a REAL DIFF.
"""
import hashlib
import sys

import duckdb

RUN_CLOCK_NAMES = ("new_value", "old_value", "detail", "head_hash")


def _digest(df) -> str:
    if len(df) and len(df.columns):
        df = df.sort_values(list(df.columns)).reset_index(drop=True)
    return hashlib.sha256(df.to_csv(index=False).encode()).hexdigest()


def table_digests(path: str) -> dict:
    con = duckdb.connect(path, read_only=True)
    out = {}
    tables = con.execute("select table_schema, table_name from information_schema.tables "
                         "where table_type = 'BASE TABLE' order by 1, 2").fetchall()
    for schema, table in tables:
        df = con.execute(f'select * from "{schema}"."{table}"').df()
        clock = [c for c in df.columns if str(df[c].dtype).startswith("datetime")
                 or c.endswith(("_at", "hash", "_ts")) or c in RUN_CLOCK_NAMES]
        out[f"{schema}.{table}"] = (len(df), _digest(df), _digest(df.drop(columns=clock)), clock)
    con.close()
    return out


def main(a_path: str, b_path: str) -> None:
    a, b = table_digests(a_path), table_digests(b_path)
    same = clock_only = real = 0
    for k in sorted(set(a) | set(b)):
        if k not in a or k not in b:
            print("MISSING", k)
            real += 1
        elif a[k][:2] == b[k][:2]:
            same += 1
        elif a[k][0] == b[k][0] and a[k][2] == b[k][2]:
            clock_only += 1
            print("differs only in excluded run-clock columns", a[k][3], k)
        else:
            real += 1
            print("REAL DIFF", k, a[k][0], b[k][0])
    print(f"tables: {len(a)}; identical {same}; differ only in timestamp/hash columns {clock_only}; "
          f"other differences {real}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
