"""Load the FAERS ASCII tables and assemble one narrative document per case.

The FAERS quarterly release is a set of `$`-delimited relational tables keyed by
``primaryid`` (DEMO, DRUG, REAC, OUTC, INDI, THER, RPSR). This module reads the
columns we need, joins them, and produces:

* a human-readable narrative string per case (used for embeddings / RAG), and
* a structured metadata record per case (used for display and report seeding).

Reading is column-pruned and string-typed to keep memory bounded even though the
DRUG table alone is ~1.7M rows.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd

import config


# FAERS files are distributed in Latin-1; a few rows contain stray bytes.
_READ_KW = dict(
    sep="$",
    dtype=str,
    keep_default_na=False,
    na_values=[],
    encoding="latin-1",
    on_bad_lines="skip",
    engine="c",
)


def _faers_path(table: str) -> Path:
    return config.FAERS_DIR / f"{table}{config.FAERS_QUARTER}.txt"


def _read_table(table: str, usecols: Iterable[str]) -> pd.DataFrame:
    path = _faers_path(table)
    if not path.exists():
        raise FileNotFoundError(f"Expected FAERS table not found: {path}")
    return pd.read_csv(path, usecols=list(usecols), **_READ_KW)


def _join_unique(series: pd.Series) -> str:
    """Join the distinct, non-empty values of a grouped column into one string."""
    seen: list[str] = []
    for value in series:
        value = (value or "").strip()
        if value and value not in seen:
            seen.append(value)
    return "; ".join(seen)


def _format_age(age: str, age_cod: str) -> str:
    age = (age or "").strip()
    if not age:
        return "Unknown"
    unit = {
        "DEC": "decades", "YR": "years", "MON": "months",
        "WK": "weeks", "DY": "days", "HR": "hours",
    }.get((age_cod or "").strip().upper(), "years")
    try:
        return f"{float(age):g} {unit}"
    except ValueError:
        return f"{age} {unit}"


def _format_weight(wt: str, wt_cod: str) -> str:
    wt = (wt or "").strip()
    if not wt:
        return "Unknown"
    unit = (wt_cod or "KG").strip().upper().lower()
    return f"{wt} {unit}"


def _format_sex(sex: str) -> str:
    return {"M": "Male", "F": "Female"}.get((sex or "").strip().upper(), "Unknown")


def build_case_frame(max_cases: int = 0) -> pd.DataFrame:
    """Build a per-case DataFrame joining all relevant FAERS tables.

    Parameters
    ----------
    max_cases:
        If > 0, only the first ``max_cases`` cases (by primaryid order) are kept.
        ``0`` means use the full dataset.

    Returns
    -------
    DataFrame indexed by ``primaryid`` with display-ready columns plus a
    ``narrative`` column suitable for embedding.
    """
    demo = _read_table(
        "DEMO",
        ["primaryid", "caseid", "age", "age_cod", "sex", "wt", "wt_cod",
         "event_dt", "rept_cod", "occr_country", "occp_cod"],
    )
    demo = demo.drop_duplicates(subset="primaryid", keep="last")
    if max_cases and max_cases > 0:
        demo = demo.head(max_cases)

    keep_ids = set(demo["primaryid"])

    def _filtered(table: str, usecols: list[str]) -> pd.DataFrame:
        frame = _read_table(table, usecols)
        return frame[frame["primaryid"].isin(keep_ids)]

    # --- Drugs: keep role and key dosing fields; flag the primary suspect. ---
    drug = _filtered(
        "DRUG",
        ["primaryid", "role_cod", "drugname", "prod_ai", "route",
         "dose_amt", "dose_unit", "dose_form", "dose_freq", "dechal", "rechal"],
    )
    primary = drug[drug["role_cod"] == "PS"]
    suspect_drug = (
        primary.groupby("primaryid")["drugname"].first()
        if not primary.empty else pd.Series(dtype=str)
    )
    all_drugs = drug.groupby("primaryid")["drugname"].agg(_join_unique)
    drug_detail = (
        primary.assign(
            _line=lambda d: d.apply(_drug_line, axis=1)
        ).groupby("primaryid")["_line"].agg(_join_unique)
    )

    reac = _filtered("REAC", ["primaryid", "pt"])
    reactions = reac.groupby("primaryid")["pt"].agg(_join_unique)

    outc = _filtered("OUTC", ["primaryid", "outc_cod"])
    outcomes = outc.groupby("primaryid")["outc_cod"].agg(_join_unique)

    indi = _filtered("INDI", ["primaryid", "indi_pt"])
    indications = indi.groupby("primaryid")["indi_pt"].agg(_join_unique)

    ther = _filtered("THER", ["primaryid", "start_dt", "end_dt"])
    ther_first = ther.groupby("primaryid").agg(
        therapy_start=("start_dt", "first"), therapy_end=("end_dt", "first")
    )

    cases = demo.set_index("primaryid").copy()
    cases["suspect_drug"] = suspect_drug
    cases["all_drugs"] = all_drugs
    cases["drug_detail"] = drug_detail
    cases["reactions"] = reactions
    cases["outcome_codes"] = outcomes
    cases["indications"] = indications
    cases = cases.join(ther_first)

    cases = cases.fillna("")
    # Fall back to first listed drug when no primary suspect is coded.
    cases["suspect_drug"] = cases.apply(
        lambda r: r["suspect_drug"] or (r["all_drugs"].split(";")[0].strip() if r["all_drugs"] else ""),
        axis=1,
    )

    cases["age_display"] = cases.apply(lambda r: _format_age(r["age"], r["age_cod"]), axis=1)
    cases["sex_display"] = cases["sex"].map(_format_sex)
    cases["weight_display"] = cases.apply(lambda r: _format_weight(r["wt"], r["wt_cod"]), axis=1)
    cases["seriousness"] = cases["outcome_codes"].map(_seriousness_label)
    cases["narrative"] = cases.apply(_build_narrative, axis=1)

    return cases


def _drug_line(row: pd.Series) -> str:
    name = (row.get("drugname") or "").strip()
    if not name:
        return ""
    parts = [name]
    dose_amt = (row.get("dose_amt") or "").strip()
    dose_unit = (row.get("dose_unit") or "").strip()
    if dose_amt:
        parts.append(f"{dose_amt} {dose_unit}".strip())
    route = (row.get("route") or "").strip()
    if route:
        parts.append(route)
    return " ".join(parts)


def _seriousness_label(codes: str) -> str:
    code_set = {c.strip().upper() for c in codes.split(";") if c.strip()}
    return "Serious" if code_set & config.SERIOUS_OUTCOME_CODES else "Non-Serious"


def _build_narrative(row: pd.Series) -> str:
    """Compose a compact clinical narrative used for semantic retrieval."""
    drugs = row["drug_detail"] or row["all_drugs"] or "Unknown"
    reactions = row["reactions"] or "Not specified"
    indications = row["indications"] or "Not specified"
    outcomes = ", ".join(
        config.OUTCOME_CODES.get(c.strip().upper(), c.strip())
        for c in row["outcome_codes"].split(";") if c.strip()
    ) or "Not specified"
    country = row.get("occr_country") or "Unknown"
    return (
        f"A {row['age_display']} {row['sex_display'].lower()} patient "
        f"(country: {country}) was treated with {drugs} "
        f"for {indications}. The patient experienced the following adverse "
        f"event(s): {reactions}. Reported outcome(s): {outcomes}. "
        f"Seriousness: {row['seriousness']}."
    )
