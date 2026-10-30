"""Paths and the QC rules config (config/qc_rules.yaml, the single source of thresholds, ADR 005)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "qc_rules.yaml"


@dataclass(frozen=True)
class Paths:
    landing: Path   # generator output (CSV + plates/)
    raw: Path       # read-only copies of the plate CSVs (AC-3.5)
    db: Path        # the one DuckDB file. Not "assay.duckdb": DuckDB names the catalog after the file, which
    #                 would clash with schema `assay` ("Ambiguous reference to catalog or schema")
    marts: Path     # Power BI exports
    img: Path       # PNG charts


def default_paths(root: Path = ROOT) -> Paths:
    root = Path(root)
    return Paths(landing=root / "data" / "landing", raw=root / "data" / "raw",
                 db=root / "data" / "warehouse" / "vaccine_assay.duckdb", marts=root / "data" / "marts",
                 img=root / "docs" / "img")


def load_rules(path: Path = CONFIG_PATH) -> dict:
    """Parsed YAML. Raises ValueError if the `version` string is missing (it is stamped on every QC flag)."""
    rules = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(rules, dict) or not rules.get("version"):
        raise ValueError(f"{path}: config has no `version` key")
    a = rules.get("assay", {})
    if {"assay_lloq_au_ml", "std_levels_au_ml", "default_dilution"} <= set(a):
        derived = min(a["std_levels_au_ml"]) * a["default_dilution"]
        if abs(a["assay_lloq_au_ml"] - derived) > 1e-6 * derived:   # ADR 003: lowest standard x default dilution
            raise ValueError(f"{path}: assay_lloq_au_ml {a['assay_lloq_au_ml']} != lowest standard x default "
                             f"dilution ({derived:g})")
    return rules


# dbt var name -> path in the YAML. These are the keys marked (dbt) in DESIGN section 5, plus the two re-assay keys
# core.reassay_list needs. dbt models read them with var('<name>').
DBT_VARS: dict[str, tuple[str, ...]] = {
    "rule_version": ("version",),
    "assay_lloq_au_ml": ("assay", "assay_lloq_au_ml"),
    "lloq_impute_factor": ("assay", "lloq_impute_factor"),
    "default_dilution": ("assay", "default_dilution"),
    "reassay_dilution_factor": ("assay", "reassay_dilution_factor"),
    "custody_steps": ("custody", "steps"),
    "max_freeze_thaw": ("custody", "max_freeze_thaw"),
    "late_entry_hours": ("alcoa", "late_entry_hours"),
    "seroresponse_fold": ("immunogenicity", "seroresponse_fold"),
    "ci_level": ("immunogenicity", "ci_level"),
    "baseline_visit": ("immunogenicity", "baseline_visit"),
    "max_unexplained_flag_pct": ("scorecard", "max_unexplained_flag_pct"),
    "expected_flags": ("scorecard", "expected_flags"),
    "required_inj_types": ("scorecard", "required_inj_types"),
    "masking_flags": ("scorecard", "masking_flags"),
}


def dbt_vars(rules: dict) -> dict:
    """The subset of the config passed to `dbt build --vars` (flat names, see DBT_VARS)."""
    out = {}
    for name, keys in DBT_VARS.items():
        node = rules
        for k in keys:
            node = node[k]
        out[name] = node
    return out
