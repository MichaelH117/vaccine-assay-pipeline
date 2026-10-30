"""Session fixtures: one full build with planted problems (`built`) and one clean build (`clean_built`), each in a
temp folder. The repo's data/ folder is never touched by tests (DESIGN section 6)."""

from __future__ import annotations

import duckdb
import pytest

from pipeline.run import build


def _built(tmp_path_factory, name: str, inject: bool):
    paths = build(tmp_path_factory.mktemp(name), seed=42, inject=inject, quiet=True)
    con = duckdb.connect(str(paths.db), read_only=True)
    truth = con.execute("select * from truth.injected_problems order by problem_id, affected_key").df()
    yield {"con": con, "paths": paths, "truth": truth}
    con.close()


@pytest.fixture(scope="session")
def built(tmp_path_factory):
    yield from _built(tmp_path_factory, "dirty", inject=True)


@pytest.fixture(scope="session")
def clean_built(tmp_path_factory):
    yield from _built(tmp_path_factory, "clean", inject=False)
