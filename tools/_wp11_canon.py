# -*- coding: utf-8 -*-
"""WP11.1 - canonical truth engine for the v11 alignment audit.

WHAT IT DOES
------------
Recomputes every number that the manuscript can legitimately derive from the
frozen pipeline outputs, and records it together with full provenance:

    metric_id | value | unit | digits | source | locator | formula | note

Sources, in the order they are read (all read-only):

    A  Climate/output/results/defense_sensitivity/defense_profile_eal.csv
    B  Climate/output/results/shanghai_city_monthly_climate_hazard.csv
    C  Climate/output/results/shanghai_city_cri_projection.csv
    D  Finance/output/results/shanghai_finance_risk_index.csv
    E  Finance/output/results/shanghai_fri_projection.csv
    F  Composite/output/results/shanghai_cfci_historical.csv
    G  Composite/output/results/shanghai_cfci_projection.csv
    H  _sensitivity_results/sensitivity_latest.csv + config/sensitivity_sweep.json
    I  the three 00_config.py files, parsed with ast (never imported: importing
       Climate/00_config.py would execute apply_sensitivity_overrides())
    J  the seven run logs of the authoritative run (run_20261017_212732).

No number in this file is typed in by hand except the *formatting* rules
(digits / unit / display suffix).  Every value is computed from a file whose
SHA256 is checked against docs/_wp11_基线.json, so a drifted source aborts the
audit instead of silently moving a "truth".

USAGE
-----
  env\\run.ps1 tools\\_wp11_canon.py                    # write docs/_wp11_真值表.csv
  env\\run.ps1 tools\\_wp11_canon.py --no-baseline      # skip the SHA check
  env\\run.ps1 tools\\_wp11_canon.py --show eal.         # print matching rows
"""

from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import io
import json
import re
import sys
from pathlib import Path

NEWROOT = Path(__file__).resolve().parent.parent
DOCS = NEWROOT / "docs"
BASELINE = DOCS / "_wp11_基线.json"
OUT_CSV = DOCS / "_wp11_真值表.csv"

CLIM = r"Climate\output\results"
FIN = r"Finance\output\results"
COMP = r"Composite\output\results"

SRC_EAL = CLIM + r"\defense_sensitivity\defense_profile_eal.csv"
SRC_HAZ = CLIM + r"\shanghai_city_monthly_climate_hazard.csv"
SRC_CRI = CLIM + r"\shanghai_city_cri_projection.csv"
SRC_HSI = FIN + r"\shanghai_finance_risk_index.csv"
SRC_HSIP = FIN + r"\shanghai_fri_projection.csv"
SRC_CCHI_H = COMP + r"\shanghai_cfci_historical.csv"
SRC_CCHI_P = COMP + r"\shanghai_cfci_projection.csv"
SRC_SENS = r"_sensitivity_results\sensitivity_latest.csv"
SRC_SWEEP = r"config\sensitivity_sweep.json"
CFG_CLIMATE = r"Climate\00_config.py"
CFG_FINANCE = r"Finance\00_config.py"
CFG_COMPOSITE = r"Composite\00_config.py"

LOGDIR = r"Climate\output\logs"
LOGS = {
    "tc": LOGDIR + r"\log_01_hazard_tc_20261017_212736.log",
    "surge": LOGDIR + r"\log_02_hazard_surge_20261017_213327.log",
    "exposure": LOGDIR + r"\log_03_exposure_20261017_213258.log",
    "vuln": LOGDIR + r"\log_04_vulnerability_20261017_213543.log",
    "risk": LOGDIR + r"\log_05_risk_20261017_213548.log",
    "defense": LOGDIR + r"\log_06_defense_sensitivity_20261017_214009.log",
    "cri": LOGDIR + r"\log_07_climate_index_20261017_214943.log",
}

SCEN3 = ("hist", "ssp245", "ssp585")
PROF2 = ("nodef", "def")

DISTRICT_EN = {
    "Pudong": "浦东新区", "Yangpu": "杨浦区", "Minhang": "闵行区",
    "Xuhui": "徐汇区", "Hongkou": "虹口区", "Huangpu": "黄浦区",
    "Baoshan": "宝山区", "Jing'an": "静安区", "Songjiang": "松江区",
    "Putuo": "普陀区", "Jiading": "嘉定区", "Changning": "长宁区",
    "Qingpu": "青浦区", "Fengxian": "奉贤区", "Jinshan": "金山区",
    "Chongming": "崇明区",
}

# ─────────────────────────────────────────────────────────────────────────
# plumbing
# ─────────────────────────────────────────────────────────────────────────


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def read_rows(rel: str) -> list[dict]:
    p = NEWROOT / rel
    with io.open(p, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def read_json(rel: str) -> dict:
    return json.loads((NEWROOT / rel).read_text(encoding="utf-8"))


def fnum(row: dict, key: str) -> float:
    return float(row[key])


class Truth:
    """Ordered metric registry with provenance."""

    def __init__(self) -> None:
        self.rows: list[dict] = []
        self.by_id: dict[str, dict] = {}
        self.problems: list[str] = []

    def add(self, mid: str, value, unit: str, digits: int, source: str,
            locator: str = "", formula: str = "", note: str = "") -> None:
        if mid in self.by_id:
            self.problems.append("duplicate metric id: " + mid)
            return
        row = {
            "metric_id": mid,
            "value": value,
            "unit": unit,
            "digits": digits,
            "source": source,
            "locator": locator,
            "formula": formula,
            "note": note,
        }
        self.rows.append(row)
        self.by_id[mid] = row

    def get(self, mid: str, default=None):
        r = self.by_id.get(mid)
        return default if r is None else r["value"]


# ─────────────────────────────────────────────────────────────────────────
# A + B : expected annual loss (defence profiles) and exposure
# ─────────────────────────────────────────────────────────────────────────


def add_eal(t: Truth) -> None:
    rows = read_rows(SRC_EAL)

    def sel(scen_short: str, prof: str) -> list[dict]:
        scen = {"hist": "historical", "ssp245": "SSP2-4.5",
                "ssp585": "SSP5-8.5"}[scen_short]
        prof_full = {"nodef": "baseline_nodef",
                     "def": "current_def_gap"}[prof]
        out = [r for r in rows
               if r["scenario"] == scen and r["defense_profile"] == prof_full]
        if len(out) != 16:
            t.problems.append("EAL sheet: %s/%s has %d districts"
                              % (scen, prof_full, len(out)))
        return out

    def tot(rs: list[dict], field: str) -> float:
        return sum(fnum(r, field) for r in rs)

    # city EAL, 3 scenarios x 2 defence profiles
    for scen in SCEN3:
        for prof in PROF2:
            rs = sel(scen, prof)
            t.add("eal.city.%s.%s.bn" % (scen, prof), tot(rs, "EAL_compound") / 1e9,
                  "CNY billion", 1, SRC_EAL,
                  "sum over 16 districts",
                  "sum(EAL_compound)/1e9",
                  "Table 1 row %s / %s" % (scen, prof))

    # defence reduction: 1 - def/nodef
    for scen in SCEN3:
        nodef = tot(sel(scen, "nodef"), "EAL_compound")
        def_ = tot(sel(scen, "def"), "EAL_compound")
        t.add("eal.city.%s.red_pct" % scen, (1.0 - def_ / nodef) * 100.0,
              "%", 1, SRC_EAL, "16-district sums", "(1 - def/nodef)*100",
              "Table 1 Reduction column")

    # wind / surge decomposition on the no-defence profile
    for scen in SCEN3:
        rs = sel(scen, "nodef")
        comp = tot(rs, "EAL_compound")
        wind = tot(rs, "EAL_wind")
        surge = tot(rs, "EAL_surge")
        t.add("eal.city.%s.wind.bn" % scen, wind / 1e9, "CNY billion", 1,
              SRC_EAL, "sum over 16 districts", "sum(EAL_wind)/1e9")
        t.add("eal.city.%s.surge.bn" % scen, surge / 1e9, "CNY billion", 1,
              SRC_EAL, "sum over 16 districts", "sum(EAL_surge)/1e9")
        t.add("eal.city.%s.wind_share_pct" % scen, wind / comp * 100.0, "%", 0,
              SRC_EAL, "16-district sums", "wind/compound*100")
        t.add("eal.city.%s.surge_share_pct" % scen, surge / comp * 100.0, "%", 0,
              SRC_EAL, "16-district sums", "surge/compound*100")

    # scenario uplift vs the historical no-defence baseline
    base = tot(sel("hist", "nodef"), "EAL_compound")
    for scen in ("ssp245", "ssp585"):
        cur = tot(sel(scen, "nodef"), "EAL_compound")
        t.add("eal.city.%s.incr_vs_hist_pct" % scen, (cur / base - 1.0) * 100.0,
              "%", 0, SRC_EAL, "16-district sums",
              "ssp_nodef/hist_nodef - 1")

    # residual: defended SSP5-8.5 still above the historical *defended* level.
    # The Results prose (P16) compares 26.5 bn with 19.0 bn, i.e. def vs def;
    # the no-defence variant is kept only so the distinction stays auditable.
    residual = tot(sel("ssp585", "def"), "EAL_compound")
    hist_def = tot(sel("hist", "def"), "EAL_compound")
    t.add("eal.residual.ssp585_def_vs_hist_def_pct", (residual / hist_def - 1.0) * 100.0,
          "%", 1, SRC_EAL, "16-district sums", "ssp585_def/hist_def - 1",
          "the 39.5% of the Results prose")
    t.add("eal.residual.ssp585_def_vs_hist_nodef_pct", (residual / base - 1.0) * 100.0,
          "%", 1, SRC_EAL, "16-district sums", "ssp585_def/hist_nodef - 1",
          "documented alternative definition; NOT the quoted 39.5%")

    # district table (historical no-defence) and its SSP5-8.5 counterpart
    for scen in ("hist", "ssp585"):
        rs = sel(scen, "nodef")
        rs = sorted(rs, key=lambda r: -fnum(r, "EAL_compound"))
        t.add("eal.dist.%s.rank" % scen, " > ".join(r["district"] for r in rs),
              "names", 0, SRC_EAL, "16 districts sorted by EAL_compound",
              "rank", "full ranking, used for the 'top three' prose")
        for rank, r in enumerate(rs, 1):
            name = r["district"]
            t.add("eal.dist.%s.%s.bn" % (scen, name),
                  fnum(r, "EAL_compound") / 1e9, "CNY billion", 1, SRC_EAL,
                  "district=%s" % name, "EAL_compound/1e9",
                  "rank %d" % rank)
            t.add("eal.dist.%s.%s.expo_t" % (scen, name),
                  fnum(r, "exposure_total") / 1e12, "CNY trillion", 1, SRC_EAL,
                  "district=%s" % name, "exposure_total/1e12")
            t.add("eal.dist.%s.%s.ratio_permille" % (scen, name),
                  fnum(r, "EAL_ratio_pct") * 10.0, "per mille", 2, SRC_EAL,
                  "district=%s" % name, "EAL_ratio_pct*10")
        ratios = [fnum(r, "EAL_ratio_pct") * 10.0 for r in rs]
        t.add("eal.dist.%s.mean_of_ratios_permille" % scen,
              sum(ratios) / len(ratios), "per mille", 2, SRC_EAL,
              "unweighted mean over 16 districts",
              "mean(EAL_ratio_pct)*10",
              "the 0.39 per mille city-mean of the Results prose")
        t.add("eal.dist.%s.city_ratio_permille" % scen,
              tot(rs, "EAL_compound") / tot(rs, "exposure_total") * 1000.0,
              "per mille", 2, SRC_EAL, "16-district sums",
              "sum(EAL)/sum(exposure)*1000",
              "aggregate alternative; NOT the number the prose uses")

    # exposure
    hist = sel("hist", "nodef")
    t.add("exposure.total_t", tot(hist, "exposure_total") / 1e12,
          "CNY trillion", 1, SRC_EAL, "sum over 16 districts",
          "sum(exposure_total)/1e12")
    big = max(hist, key=lambda r: fnum(r, "exposure_total"))
    t.add("exposure.largest_district", big["district"], "name", 0, SRC_EAL,
          "district=%s" % big["district"], "argmax(exposure_total)",
          "the 'largest district by exposure' of the Results prose")
    runner = sorted(hist, key=lambda r: -fnum(r, "exposure_total"))[1]
    t.add("exposure.second_district_t", fnum(runner, "exposure_total") / 1e12,
          "CNY trillion", 2, SRC_EAL, "district=%s" % runner["district"],
          "exposure_total/1e12", "runner-up, i.e. how clear the lead is")


# ─────────────────────────────────────────────────────────────────────────
# dependence between the two indices (the rho of the composite section)
# ─────────────────────────────────────────────────────────────────────────


def _rank(v: list) -> list:
    order = sorted(range(len(v)), key=lambda i: v[i])
    r = [0.0] * len(v)
    i = 0
    while i < len(v):
        j = i
        while j + 1 < len(v) and v[order[j + 1]] == v[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            r[order[k]] = avg
        i = j + 1
    return r


def _pearson(a: list, b: list) -> float:
    n = len(a)
    ma, mb = sum(a) / n, sum(b) / n
    sa = sum((x - ma) ** 2 for x in a) ** 0.5
    sb = sum((x - mb) ** 2 for x in b) ** 0.5
    return sum((a[i] - ma) * (b[i] - mb) for i in range(n)) / (sa * sb)


def add_dependence(t: Truth) -> None:
    hist = read_rows(SRC_CCHI_H)
    xs = [float(r["cri_index"]) for r in hist]
    ys = [float(r["fri_index"]) for r in hist]
    t.add("dep.spearman", _pearson(_rank(xs), _rank(ys)), "rho", 3,
          SRC_CCHI_H, "%s..%s (%d months)" % (hist[0]["date"][:7],
                                             hist[-1]["date"][:7], len(hist)),
          "Spearman rank correlation of the CRI and HSI monthly series",
          "the empirical *rank* correlation the manuscript calls 0.358")
    t.add("dep.pearson", _pearson(xs, ys), "r", 3, SRC_CCHI_H,
          "%s..%s (%d months)" % (hist[0]["date"][:7], hist[-1]["date"][:7],
                                  len(hist)),
          "Pearson correlation of the same two series",
          "the linear analogue; compare with the figure annotation")
    t.add("dep.n_months", len(hist), "months", 0, SRC_CCHI_H,
          "rows of shanghai_cfci_historical.csv", "len(rows)",
          "the 2011-2023 overlap window")
    t.add("dep.start_year", int(hist[0]["date"][:4]), "year", 0, SRC_CCHI_H,
          "first row", "year")
    t.add("dep.end_year", int(hist[-1]["date"][:4]), "year", 0, SRC_CCHI_H,
          "last row", "year")
    t.add("cchi.hist.start_year", int(hist[0]["date"][:4]), "year", 0,
          SRC_CCHI_H, "first row", "year")
    t.add("cchi.hist.end_year", int(hist[-1]["date"][:4]), "year", 0,
          SRC_CCHI_H, "last row", "year")


# ─────────────────────────────────────────────────────────────────────────
# C : historical CRI + CRI projection
# ─────────────────────────────────────────────────────────────────────────


def _month_row(rows: list[dict], date: str, key="date") -> dict:
    for r in rows:
        if r[key][:7] == date:
            return r
    raise KeyError(date)


def add_cri(t: Truth) -> None:
    haz = [r for r in read_rows(SRC_HAZ)
           if r["cri_index"].strip() not in ("", "nan")]
    first, last = haz[0], haz[-1]
    t.add("cri.hist.start", float(first["cri_index"]), "index", 1, SRC_HAZ,
          "date=%s (first valid; EWMA warm-up)" % first["date"], "cri_index",
          "index starts at CRI_BASE_INDEX=100")
    t.add("cri.hist.2023_12", float(last["cri_index"]), "index", 1, SRC_HAZ,
          "date=%s" % last["date"], "cri_index",
          "the 440.3 quoted in the Results")
    t.add("cri.hist.fold", float(last["cri_index"]) / float(first["cri_index"]),
          "ratio", 1, SRC_HAZ, "%s vs %s" % (last["date"], first["date"]),
          "end/start", "the '4.4-fold' of the Results")
    t.add("cri.hist.max", max(float(r["cri_index"]) for r in haz), "index", 1,
          SRC_HAZ, "max over the historical series", "max(cri_index)")
    t.add("cri.hist.first_year", int(first["year"]), "year", 0, SRC_HAZ,
          "first valid row", "year")
    t.add("cri.hist.last_year", int(last["year"]), "year", 0, SRC_HAZ,
          "last valid row", "year")

    proj = read_rows(SRC_CRI)
    end = "2050-12"
    for scen, label in (("hist", "Historical Baseline"), ("ssp245", "SSP2-4.5"),
                        ("ssp585", "SSP5-8.5")):
        r = _month_row([x for x in proj if x["scenario"] == label], end)
        for p in ("p10", "p50", "p90"):
            t.add("cri.proj.%s.%s" % (scen, p), float(r["cri_index_" + p]),
                  "index", 0, SRC_CRI,
                  "scenario=%s date=%s" % (label, end), "cri_index_" + p,
                  "Table 3 column %s" % p)
        t.add("cri.proj.%s.rep" % scen, float(r["cri_index_rep"]), "index", 0,
              SRC_CRI, "scenario=%s date=%s" % (label, end), "cri_index_rep")

    # The Results prose (P42) expresses the SSP uplift relative to the 2050
    # *historical-baseline* median (601 -> 675 / 745), not relative to 2023-12.
    base2050 = t.get("cri.proj.hist.p50")
    terminal = float(last["cri_index"])
    for scen in ("ssp245", "ssp585"):
        p50 = t.get("cri.proj.%s.p50" % scen)
        t.add("cri.incr.%s.p50_vs_hist2050_pct" % scen,
              (p50 / base2050 - 1.0) * 100.0, "%", 1, SRC_CRI,
              "2050-12 p50 vs the historical-baseline 2050 p50",
              "p50_scen/p50_hist - 1", "the 12.4% / 23.9% of the Results")
        t.add("cri.incr.%s.p50_vs_2023_pct" % scen,
              (p50 / terminal - 1.0) * 100.0, "%", 1, SRC_CRI,
              "2050-12 p50 vs the 2023-12 terminal value",
              "p50_2050/cri_2023_12 - 1",
              "documented alternative definition; NOT the quoted increment")


# ─────────────────────────────────────────────────────────────────────────
# D + E : HSI (housing stress index == the manuscript's HSI / FRI)
# ─────────────────────────────────────────────────────────────────────────


def add_hsi(t: Truth) -> None:
    hsi = read_rows(SRC_HSI)
    idx = [(r["date"], float(r["fri_index"])) for r in hsi
           if r["fri_index"].strip() not in ("", "nan")]
    peak_date, peak = max(idx, key=lambda kv: kv[1])
    t.add("hsi.hist.peak", peak, "index", 0, SRC_HSI, "date=%s" % peak_date,
          "max(fri_index)", "the peak quoted in the Results")
    t.add("hsi.hist.last", idx[-1][1], "index", 0, SRC_HSI,
          "date=%s (end of the series)" % idx[-1][0], "fri_index",
          "the terminal HSI quoted in the Results")
    t.add("hsi.hist.first", idx[0][1], "index", 1, SRC_HSI,
          "date=%s" % idx[0][0], "fri_index", "index base")
    t.add("hsi.hist.2023_12", float(_month_row(hsi, "2023-12")["fri_index"]),
          "index", 0, SRC_HSI, "date=2023-12", "fri_index")
    t.add("hsi.hist.first_year", int(idx[0][0][:4]), "year", 0, SRC_HSI,
          "first valid row", "year")
    t.add("hsi.hist.last_year", int(idx[-1][0][:4]), "year", 0, SRC_HSI,
          "last valid row", "year")
    t.add("hsi.hist.peak_year", int(peak_date[:4]), "year", 0, SRC_HSI,
          "argmax row", "year")

    proj = read_rows(SRC_HSIP)
    end = "2050-12"
    for scen, label in (("hist", "Historical Baseline"), ("ssp245", "SSP2-4.5"),
                        ("ssp585", "SSP5-8.5")):
        r = _month_row([x for x in proj if x["scenario"] == label], end)
        for p in ("p10", "p50", "p90"):
            t.add("hsi.proj.%s.%s" % (scen, p), float(r["fri_index_" + p]),
                  "index", 0, SRC_HSIP,
                  "scenario=%s date=%s" % (label, end), "fri_index_" + p,
                  "Table 4 column %s" % p)


# ─────────────────────────────────────────────────────────────────────────
# F + G : CCHI (composite)
# ─────────────────────────────────────────────────────────────────────────


def add_cchi(t: Truth) -> None:
    hist = read_rows(SRC_CCHI_H)
    first, last = hist[0], hist[-1]
    t.add("cchi.hist.first", float(first["cfci"]), "index", 0, SRC_CCHI_H,
          "date=%s" % first["date"], "cfci", "first historical CCHI")
    t.add("cchi.hist.2023_12", float(last["cfci"]), "index", 1, SRC_CCHI_H,
          "date=%s" % last["date"], "cfci", "the 313 quoted in the Results")
    t.add("cchi.hist.first_cri", float(first["cri_index"]), "index", 1,
          SRC_CCHI_H, "date=%s" % first["date"], "cri_index")
    t.add("cchi.hist.first_hsi", float(first["fri_index"]), "index", 1,
          SRC_CCHI_H, "date=%s" % first["date"], "fri_index")

    proj = read_rows(SRC_CCHI_P)
    end = "2050-12"
    for scen, label in (("hist", "Historical Baseline"), ("ssp245", "SSP2-4.5"),
                        ("ssp585", "SSP5-8.5")):
        r = _month_row([x for x in proj if x["scenario"] == label], end)
        for p in ("p10", "p50", "p90"):
            t.add("cchi.proj.%s.%s" % (scen, p), float(r["cfci_" + p]),
                  "index", 0, SRC_CCHI_P,
                  "scenario=%s date=%s" % (label, end), "cfci_" + p,
                  "Table 5 column %s" % p)

    terminal = float(last["cfci"])
    for scen in ("ssp245", "ssp585"):
        p50 = t.get("cchi.proj.%s.p50" % scen)
        t.add("cchi.incr.%s.p50_pct" % scen, (p50 / terminal - 1.0) * 100.0,
              "%", 0, SRC_CCHI_P, "2050-12 p50 vs %s" % last["date"],
              "p50_2050/cfci_2023_12 - 1",
              "the '53%' of the Abstract")


# ─────────────────────────────────────────────────────────────────────────
# H : Table 8 (sensitivity) - one row per swept parameter
# ─────────────────────────────────────────────────────────────────────────

# docx row -> (sweep_id, index column, format kind, primary index)
T8_ROWS = [
    (2, "SURGE_MDR_CALIBRATION_SCALE", "DEF_EAL_historical_baseline_nodef", "bn", "EAL"),
    (3, "TC_V_HALF_BASE_SCALE", "DEF_EAL_historical_baseline_nodef", "bn", "EAL"),
    (4, "TC_IMPACT_V_THRESH", "DEF_EAL_historical_baseline_nodef", "bn", "EAL"),
    (5, "GAMMA_SVI", "DEF_EAL_historical_baseline_nodef", "bn", "EAL"),
    (6, "V_HALF_ADJ_A_old", "DEF_EAL_historical_baseline_nodef", "bn", "EAL"),
    (7, "V_HALF_ADJ_A_new", "DEF_EAL_historical_baseline_nodef", "bn", "EAL"),
    (8, "V_HALF_ADJ_B_old", "DEF_EAL_historical_baseline_nodef", "bn", "EAL"),
    (9, "V_HALF_ADJ_B_new", "DEF_EAL_historical_baseline_nodef", "bn", "EAL"),
    (10, "V_HALF_ADJ_C", "DEF_EAL_historical_baseline_nodef", "bn", "EAL"),
    (11, "V_HALF_ADJ_D", "DEF_EAL_historical_baseline_nodef", "bn", "EAL"),
    (13, "CRI_EWMA_ALPHA", "CRI_2050_p50_Historical Baseline", "int", "CRI"),
    (14, "CRI_DAMAGE_KAPPA", "CRI_2050_p50_Historical Baseline", "int", "CRI"),
    (15, "HP_LAMBDA", "FRI_2050_p50_Historical Baseline", "int", "HSI"),
    (16, "VOLATILITY_WINDOW", "FRI_2050_p50_Historical Baseline", "int", "HSI"),
    (17, "CFI_WEIGHT_SLA", "CRI_2050_p50_Historical Baseline", "int", "CRI"),
    (18, "FRI_WEIGHT_GAP", "FRI_2050_p50_Historical Baseline", "int", "HSI"),
    (20, "CFCI_TARGET_RHO", "CFCI_2050_p50_Historical Baseline", "int", "CCHI"),
]

# how the "max deviation" column is printed, per docx row
T8_DEV_FMT = {
    2: (0, False), 3: (0, False), 4: (0, False), 5: (0, False),
    6: (0, False), 7: (0, False), 8: (0, False), 9: (0, False),
    10: (0, "zero"), 11: (0, False),
    13: (1, "pm"), 14: (1, False),
    15: (0, False), 16: (1, False), 17: (1, False), 18: (0, False),
    20: (1, False),
}


def add_table8(t: Truth) -> None:
    sens = read_rows(SRC_SENS)
    sweep = read_json(SRC_SWEEP)["sweeps"]
    spec = {s["id"]: s for s in sweep}
    by_sweep: dict[str, list[dict]] = {}
    for r in sens:
        by_sweep.setdefault(r["sweep_id"], []).append(r)

    for row, sid, col, kind, primary in T8_ROWS:
        rs = by_sweep.get(sid)
        if not rs:
            t.problems.append("Table 8: sweep %s missing" % sid)
            continue
        base_rows = [r for r in rs if r["is_baseline"] == "True"]
        if not base_rows:
            base_rows = [rs[len(rs) // 2]]
        base = fnum(base_rows[0], col)
        vals = [fnum(r, col) for r in rs]
        lo, hi = min(vals), max(vals)
        scale = 1e9 if kind == "bn" else 1.0
        t.add("t8.r%d.index_baseline" % row, base / scale,
              "CNY billion" if kind == "bn" else "index",
              1 if kind == "bn" else 0, SRC_SENS,
              "sweep=%s is_baseline" % sid, col)
        t.add("t8.r%d.index_min" % row, lo / scale,
              "CNY billion" if kind == "bn" else "index",
              1 if kind == "bn" else 0, SRC_SENS,
              "sweep=%s over %d values" % (sid, len(vals)), "min(%s)" % col)
        t.add("t8.r%d.index_max" % row, hi / scale,
              "CNY billion" if kind == "bn" else "index",
              1 if kind == "bn" else 0, SRC_SENS,
              "sweep=%s over %d values" % (sid, len(vals)), "max(%s)" % col)
        t.add("t8.r%d.dev_min" % row, (lo - base) / base * 100.0, "%",
              T8_DEV_FMT[row][0], SRC_SENS, "sweep=%s" % sid,
              "(min-baseline)/baseline*100")
        t.add("t8.r%d.dev_max" % row, (hi - base) / base * 100.0, "%",
              T8_DEV_FMT[row][0], SRC_SENS, "sweep=%s" % sid,
              "(max-baseline)/baseline*100")
        t.add("t8.r%d.primary" % row, primary, "text", 0, SRC_SENS, sid,
              "primary index of the sweep")
        # baseline + tested range of the parameter itself (sweep spec)
        sp = spec.get(sid, {})
        if "values" in sp:
            t.add("t8.r%d.param_baseline" % row, sp["baseline"], "param", 3,
                  SRC_SWEEP, "sweeps[%s].baseline" % sid, "literal")
            t.add("t8.r%d.param_lo" % row, min(sp["values"]), "param", 3,
                  SRC_SWEEP, "sweeps[%s].values" % sid, "min(values)")
            t.add("t8.r%d.param_hi" % row, max(sp["values"]), "param", 3,
                  SRC_SWEEP, "sweeps[%s].values" % sid, "max(values)")
        elif "values_tuples" in sp:
            t.add("t8.r%d.param_baseline" % row, sp["baseline"], "param", 3,
                  SRC_SWEEP, "sweeps[%s].baseline" % sid, "literal")
            t.add("t8.r%d.param_tuples" % row,
                  "; ".join(str(t2) for t2 in sp["values_tuples"]),
                  "text", 0, SRC_SWEEP, "sweeps[%s].values_tuples" % sid, "literal")

    # every tested value, one metric each (the figure captions quote the full
    # list, e.g. "[0.95, 0.975, 1.0, 1.025, 1.05]")
    for sp in sweep:
        if "values" not in sp:
            continue
        for i, v in enumerate(sp["values"]):
            t.add("sweep.%s.v%d" % (sp["id"], i), float(v), "param", 6,
                  SRC_SWEEP, "sweeps[%s].values[%d]" % (sp["id"], i), "literal")
        t.add("sweep.%s.n" % sp["id"], len(sp["values"]), "count", 0,
              SRC_SWEEP, "sweeps[%s].values" % sp["id"], "len(values)")
    for sp in sweep:
        for i, tup in enumerate(sp.get("values_tuples", [])):
            for j, v in enumerate(tup):
                t.add("sweep.%s.v%d.%d" % (sp["id"], i, j), float(v), "weight",
                      3, SRC_SWEEP,
                      "sweeps[%s].values_tuples[%d][%d]" % (sp["id"], i, j),
                      "literal")


# ─────────────────────────────────────────────────────────────────────────
# I : config constants (ast, never imported)
# ─────────────────────────────────────────────────────────────────────────


def config_literals(rel: str) -> dict:
    src = (NEWROOT / rel).read_text(encoding="utf-8")
    tree = ast.parse(src)
    out: dict = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        try:
            out[target.id] = (ast.literal_eval(node.value), node.lineno)
        except (ValueError, SyntaxError):
            continue
    return out


def add_params(t: Truth) -> None:
    for rel in (CFG_CLIMATE, CFG_FINANCE, CFG_COMPOSITE):
        mod = Path(rel).parent.name
        for name, (value, lineno) in config_literals(rel).items():
            t.add("p.%s.%s" % (mod, name), value, "param", 6, rel,
                  "line %d" % lineno, "ast literal")

    # The AAL calibration ratio is not computed by v8: it survives only as a
    # comment recording the v6 validation.  Recorded here so the manuscript
    # number has a citable origin, with the provenance limit made explicit.
    src = (NEWROOT / CFG_CLIMATE).read_text(encoding="utf-8")
    m = re.search(r"AAL pred/obs = ([0-9.]+) for (\d{4})-(\d{4})", src)
    if m:
        t.add("calib.aal_pred_obs", float(m.group(1)), "ratio", 4, CFG_CLIMATE,
              "source comment (v6 04b validation)", "literal from comment",
              "NOT recomputed by the v8 pipeline; window %s-%s"
              % (m.group(2), m.group(3)))
        t.add("calib.window_start", int(m.group(2)), "year", 0, CFG_CLIMATE,
              "source comment", "literal from comment")
        t.add("calib.window_end", int(m.group(3)), "year", 0, CFG_CLIMATE,
              "source comment", "literal from comment")
    else:
        t.problems.append("AAL calibration ratio comment not found")


# ─────────────────────────────────────────────────────────────────────────
# J : run-log facts (the only provenance for derived runtime quantities)
# ─────────────────────────────────────────────────────────────────────────

# metric_id -> (log key, regex, group index, unit, digits, note)
LOG_FACTS = [
    ("log.tc.n_tracks_all", "tc", r"Loaded (\d+) WP tracks", 1, "count", 0, ""),
    ("log.tc.n_tracks_hist", "tc", r"Filtered: (\d+)/(\d+) tracks affect Shanghai", 1,
     "count", 0, "the 107 historical events"),
    ("log.tc.n_synth_total", "tc", r"Synthetic: (\d+) tracks", 1, "count", 0, ""),
    ("log.tc.knutson_ssp245", "tc",
     r"SSP2-4\.5: intensity factor = ([0-9.]+)", 1, "factor", 4,
     "effective Knutson WP intensity factor at 2050"),
    ("log.tc.knutson_ssp585", "tc",
     r"SSP5-8\.5: intensity factor = ([0-9.]+)", 1, "factor", 4,
     "effective Knutson WP intensity factor at 2050"),
    ("log.tc.temp_slope", "tc", r"Temp trend: slope=([0-9.]+) C/yr", 1,
     "degC/yr", 6, ""),
    ("log.tc.alpha_min", "tc", r"alpha range \[([0-9.]+), ([0-9.]+)\]", 1,
     "factor", 4, ""),
    ("log.tc.alpha_max", "tc", r"alpha range \[([0-9.]+), ([0-9.]+)\]", 2,
     "factor", 4, ""),
    ("log.tc.max_wind", "tc", r"Hist wind: \d+ events, max=([0-9.]+) m/s", 1,
     "m/s", 1, ""),
    ("log.risk.n_buildings", "risk", r"Buildings: ([\d,]+)", 1, "count", 0, ""),
    ("log.risk.risk_panel_rows", "risk", r"Risk panel: ([\d,]+) rows", 1,
     "count", 0, ""),
    ("log.exp.n_buildings", "exposure", r"Total buildings loaded: ([\d,]+)", 1,
     "count", 0, ""),
    ("log.exp.age_filled", "exposure",
     r"Age enrichment from Lianjia: ([\d,]+) buildings", 1, "count", 0,
     "buildings whose age comes from the POI join"),
    ("log.exp.price_level1", "exposure", r"L1 Lianjia match: ([\d,]+)/([\d,]+)", 1,
     "count", 0, ""),
    ("log.exp.price_level2", "exposure",
     r"Price tiers: \{1: (\d+), 2: (\d+)\}", 2, "count", 0, ""),
    ("log.exp.commercial_n", "exposure",
     r"Commercial adjustment: ([\d,]+) buildings", 1, "count", 0, ""),
    ("log.exp.commercial_capped", "exposure",
     r"(\d[\d,]*) footprints capped at 5000m2", 1, "count", 0, ""),
    ("log.exp.exposure_trillion", "exposure",
     r"Total exposure: ([0-9.]+) trillion CNY", 1, "CNY trillion", 2, ""),
    ("log.exp.city_price", "exposure",
     r"City-wide latest price: ([0-9.]+) CNY/m2", 1, "CNY/m2", 0, ""),
    ("log.surge.slr_245", "surge", r"SSP2-4\.5: SLR \+([0-9.]+)m", 1, "m", 1, ""),
    ("log.surge.slr_585", "surge", r"SSP5-8\.5: SLR \+([0-9.]+)m", 1, "m", 1, ""),
    ("log.surge.shelf_L", "surge", r"Shelf params: L=([0-9.]+)m", 1, "m", 0, ""),
    ("log.surge.shelf_h", "surge", r"Shelf params: L=[0-9.]+m, h=([0-9.]+)m", 1,
     "m", 1, ""),
    ("log.surge.elev_mean", "surge", r"Building elevation: mean=([0-9.]+)m", 1,
     "m", 1, ""),
    ("log.surge.elev_low_pct", "surge", r"low\(≤3m\)=([0-9.]+)%", 1, "%", 1, ""),
    ("log.surge.huangpu_nonzero_def", "surge",
     r"nonzero=74924, max=([0-9.]+)m, bankfull=([0-9.]+), decay=([0-9.]+)m", 1,
     "m", 2, ""),
    ("log.surge.huangpu_decay_def", "surge",
     r"nonzero=74924, max=[0-9.]+m, bankfull=[0-9.]+, decay=([0-9.]+)m", 1,
     "m", 0, ""),
    ("log.surge.huangpu_decay_nodef", "defense",
     r"nonzero=37198, max=[0-9.]+m, bankfull=[0-9.]+, decay=([0-9.]+)m", 1,
     "m", 0, ""),
    ("log.vuln.vhalf_base", "vuln", r"WP3 base v_half = ([0-9.]+) m/s", 1,
     "m/s", 1, ""),
    ("log.vuln.mdr_scale", "vuln",
     r"SURGE_MDR_CALIBRATION_SCALE = ([0-9.]+)", 1, "factor", 3, ""),
    ("log.vuln.pca_var", "vuln", r"PCA variance explained: ([0-9.]+)", 1,
     "fraction", 4, ""),
    ("log.cri.cri_end", "cri", r"CRI index \(base 100\): start=[0-9.]+, end=([0-9.]+)",
     1, "index", 1, ""),
    ("log.cri.eal", "cri", r"EAL=([0-9.e+]+)/yr", 1, "CNY/yr", 0, ""),
    ("log.cri.hist_mean", "cri", r"CRI raw: mean=([0-9.]+)", 1, "raw", 4, ""),
    ("log.cri.slow_theta", "cri", r"Z-slow: \S+=([0-9.]+)", 1, "per month", 3, ""),
    ("log.cri.slow_sigma", "cri", r"Z-slow: \S+=[0-9.]+, \S+=([0-9.]+)", 1,
     "per month", 5, ""),
]


def add_logfacts(t: Truth) -> None:
    cache: dict[str, str] = {}
    for mid, key, pattern, grp, unit, digits, note in LOG_FACTS:
        rel = LOGS[key]
        if rel not in cache:
            p = NEWROOT / rel
            cache[rel] = p.read_text(encoding="utf-8", errors="replace") if p.is_file() else ""
        text = cache[rel]
        if not text:
            t.problems.append("log missing: %s" % rel)
            continue
        m = re.search(pattern, text)
        if not m:
            t.problems.append("log fact not found: %s (%s)" % (mid, pattern))
            continue
        raw = m.group(grp).replace(",", "")
        try:
            value = float(raw)
        except ValueError:
            value = raw
        t.add(mid, value, unit, digits, rel, "regex %d" % grp, pattern, note)

    # derived from two log facts: the synthetic tracks added on top of the
    # historical catalogue (NB_SYNTH_TRACKS=10 per historical track)
    n_hist = t.get("log.tc.n_tracks_hist")
    n_all = t.get("log.tc.n_synth_total")
    if isinstance(n_hist, float) and isinstance(n_all, float):
        t.add("log.tc.n_synth_added", n_all - n_hist, "count", 0,
              LOGS["tc"], "1177 - 107", "n_synth_total - n_tracks_hist",
              "the 1,070 of the Results prose")

    # CVaR realisation count = historical tracks x (1 + perturbations) - 1 cast
    n_per = t.get("cvar.n_perturb")
    if isinstance(n_hist, float) and isinstance(n_per, float):
        t.add("cvar.n_realisations", n_hist * (n_per + 1.0), "count", 0,
              LOGS["tc"], "107 x 101", "n_tracks_hist*(n_perturb+1)",
              "the 10,807 realisations of the Methods")

    # age-proxy remainder = buildings - age-enriched buildings
    n_b = t.get("log.exp.n_buildings")
    n_age = t.get("log.exp.age_filled")
    if isinstance(n_b, float) and isinstance(n_age, float):
        t.add("log.exp.age_proxy", n_b - n_age, "count", 0, LOGS["exposure"],
              "585033 - 429906", "n_buildings - age_filled",
              "the 155,127 of the Data section")
        t.add("log.exp.age_coverage_pct", n_age / n_b * 100.0, "%", 1,
              LOGS["exposure"], "429906/585033", "age_filled/n_buildings*100",
              "the 73.5% of the Data and Limitations sections")


def add_data_windows(t: Truth) -> None:
    """Coverage windows are encoded in the configured source-directory names,
    so they can be verified instead of trusted.  The paths are Path(...) / "str"
    expressions, which ast.literal_eval cannot fold, so the years are read from
    the source line itself."""
    src = (NEWROOT / CFG_CLIMATE).read_text(encoding="utf-8")
    line_years = {}
    for line in src.splitlines():
        m = re.match(r"\s*([A-Z][A-Z0-9_]*)\s*=", line)
        if not m:
            continue
        y = re.search(r"(\d{4})-(\d{4})", line)
        if y:
            line_years[m.group(1)] = (int(y.group(1)), int(y.group(2)))

    targets = [
        ("landscan", "LANDSCAN_DIR", "annual ambient population raster"),
        ("isr", "ISR_DIR", "impervious-surface-ratio raster"),
        ("temp", "TMIN_RASTER_DIR", "monthly minimum-temperature raster"),
        ("sla", "SLA_DIR", "monthly sea-level-anomaly raster"),
        ("dprice", "DISTRICT_PRICE_DIR", "district monthly price panel"),
        ("cprice", "CITY_PRICE_DIR", "city monthly price panel"),
        ("wind", "WIND_RASTER_DIR", "monthly wind raster"),
        ("precip", "PRECIP_RASTER_DIR", "monthly precipitation raster"),
    ]
    for key, name, label in targets:
        if name not in line_years:
            t.problems.append("source-directory years not found: %s" % name)
            continue
        y0, y1 = line_years[name]
        for tag, val in (("y0", y0), ("y1", y1)):
            t.add("data.%s.%s" % (key, tag), val, "year", 0, CFG_CLIMATE,
                  "%s line carries %d-%d" % (name, y0, y1), "regex", label)
    for tag in ("y0", "y1"):
        v = t.get("data.temp." + tag)
        if v is not None:
            t.add("data.tempbase." + tag, v, "year", 0, CFG_CLIMATE,
                  "TMIN_RASTER_DIR", "regex",
                  "anomaly baseline of the warming elasticity")

    # FRI estimation window actually present in the frozen output
    hsi = [r for r in read_rows(SRC_HSI)
           if r["fri_index"].strip() not in ("", "nan")]
    if hsi:
        t.add("data.fri_start_year", int(hsi[0]["date"][:4]), "year", 0,
              SRC_HSI, "first valid fri_index", "year")
        t.add("data.fri_end_year", int(hsi[-1]["date"][:4]), "year", 0,
              SRC_HSI, "last valid fri_index", "year")
    if t.get("data.isr.y0") is not None and t.get("data.isr.y1") is not None:
        n = int((t.get("data.isr.y1") - t.get("data.isr.y0")) / 5) + 1
        t.add("data.isr.epoch_n", n, "count", 0, CFG_CLIMATE,
              "(y1-y0)/5+1", "derived", "the eight ISR epochs")
    proj = read_rows(SRC_CRI)
    t.add("cri.proj.start_year", min(int(r["year"]) for r in proj), "year", 0,
          SRC_CRI, "min(year)", "year", "the 2024 of the section title")


def add_exposure_constants(t: Truth) -> None:
    """Constants hard-coded in 03_exposure.py (not in 00_config.py)."""
    rel = r"Climate\03_exposure.py"
    src = (NEWROOT / rel).read_text(encoding="utf-8")
    for mid, pattern, digits in (
        ("exposure.age_match_radius_m", r"max_dist_age_deg = (\d+) / 111000", 0),
        ("exposure.commercial_area_cap_m2", r"COMMERCIAL_FOOTPRINT_CAP_M2 = ([0-9.]+)", 0),
        ("exposure.commercial_cost_cny_m2", r"COMMERCIAL_CONSTRUCTION_COST = ([0-9.]+)", 0),
    ):
        m = re.search(pattern, src)
        if m:
            t.add(mid, float(m.group(1)), "m2" if "area" in mid or "cost" in mid
                  else "m", digits, rel, "literal %r" % pattern,
                  "regex on the module source")
        else:
            t.problems.append("exposure constant not found: %s" % mid)


def add_misc_facts(t: Truth) -> None:
    """Small facts that the prose states and that the run records directly."""
    rel_tc = r"Climate\01_hazard_tc.py"
    src_tc = (NEWROOT / rel_tc).read_text(encoding="utf-8")
    m = re.search(r"baseline=\((\d{4}),\s*(\d{4})\)", src_tc)
    if m:
        t.add("knutson.baseline_start", int(m.group(1)), "year", 0, rel_tc,
              "get_knutson_scaling_factor(baseline=...)", "regex")
        t.add("knutson.baseline_end", int(m.group(2)), "year", 0, rel_tc,
              "get_knutson_scaling_factor(baseline=...)", "regex")
    m = re.search(r'percentile="(\d+)"', src_tc)
    if m:
        t.add("knutson.percentile", int(m.group(1)), "percentile", 0, rel_tc,
              "get_knutson_scaling_factor(percentile=...)", "regex")
    m = re.search(r'year"\] >= (\d{4})\) & \(annual\["year"\] <= (\d{4})\)', src_tc)
    if not m:
        m = re.search(r'>= (\d{4})\) & \(annual\["year"\] <= (\d{4})', src_tc)
    if m:
        t.add("temp.anomaly.base_y0", int(m.group(1)), "year", 0, rel_tc,
              "annual temperature anomaly baseline", "regex",
              "the 1990-2020 reference period")
        t.add("temp.anomaly.base_y1", int(m.group(2)), "year", 0, rel_tc,
              "annual temperature anomaly baseline", "regex",
              "the 1990-2020 reference period")
    clim = config_literals(CFG_CLIMATE)
    if "SHANGHAI_DISTRICTS" in clim:
        t.add("districts.n", len(clim["SHANGHAI_DISTRICTS"][0]), "count", 0,
              CFG_CLIMATE, "len(SHANGHAI_DISTRICTS)", "len()",
              "the 16 municipal districts")
    v6 = t.get("calib.aal_pred_obs")
    shift = t.get("boundary.hist_nodef_vs_legacy_pct")
    if isinstance(v6, float) and isinstance(shift, float):
        t.add("calib.aal_pred_obs_v8", v6 * (1.0 + shift / 100.0), "ratio", 4,
              CFG_CLIMATE, "v6 ratio scaled by the boundary offset",
              "v6_ratio * (1 + boundary.hist_nodef_vs_legacy_pct/100)",
              "expectation for the official boundary; the observed-loss "
              "workbook in data/ carries no Shanghai row, so the ratio cannot "
              "be recomputed from data - the manuscript states it as ~1.00")
    risk = (NEWROOT / LOGS["risk"]).read_text(encoding="utf-8", errors="replace")
    m = re.search(r"years: (\d{4})-(\d{4})", risk)
    if m:
        t.add("log.tc.year_min", int(m.group(1)), "year", 0, LOGS["risk"],
              "events window", "regex")
        t.add("log.tc.year_max", int(m.group(2)), "year", 0, LOGS["risk"],
              "events window", "regex")
    else:
        t.problems.append("event year window not found in the risk log")


def add_derived_params(t: Truth) -> None:
    """Flatten the structured config literals into one scalar metric per value.

    Tables 6, 7 and B1 quote individual dict entries (a v_half multiplier, one
    depth-damage node, one defence-profile crest), so the audit needs a metric id
    per scalar rather than one per Python object.
    """
    clim = config_literals(CFG_CLIMATE)
    fin = config_literals(CFG_FINANCE)

    def g(name, default=None):
        return clim[name][0] if name in clim else default

    # defence profiles
    for prof in g("DEFENSE_PROFILES", []):
        for key in ("coastal_defense_crest_m", "huangpu_trigger_twl_m",
                    "huangpu_reference_twl_m", "huangpu_full_response_twl_m"):
            if key in prof:
                t.add("defence.%s.%s" % (prof["profile_name"], key),
                      float(prof[key]), "m", 2, CFG_CLIMATE,
                      "DEFENSE_PROFILES[%s].%s" % (prof["profile_name"], key),
                      "literal")
    nodef = [p for p in g("DEFENSE_PROFILES", []) if p["profile_name"] == "baseline_nodef"]
    if nodef:
        t.add("defence.nodef.huangpu_decay_m",
              float(g("HYBRID_HUANGPU_NODEF_DECAY_DISTANCE_M")), "m", 0,
              CFG_CLIMATE, "HYBRID_HUANGPU_NODEF_DECAY_DISTANCE_M", "literal")
    if "L_SHELF_M" in clim:
        t.add("shelf.width_km", float(clim["L_SHELF_M"][0]) / 1000.0, "km", 0,
              CFG_CLIMATE, "L_SHELF_M / 1000", "unit conversion",
              "Table B1 reports the shelf width in km")

    # per-category v_half adjustment / surge class / classification rules
    for cat, v in g("V_HALF_ADJUSTMENT", {}).items():
        t.add("vhalf.adj.%s" % cat, float(v), "factor", 2, CFG_CLIMATE,
              "V_HALF_ADJUSTMENT.%s" % cat, "literal", "Table 6 Adjustment")
    for cat, cls in g("CATEGORY_TO_SURGE_CLASS", {}).items():
        t.add("vhalf.class.%s" % cat, cls, "text", 0, CFG_CLIMATE,
              "CATEGORY_TO_SURGE_CLASS.%s" % cat, "literal",
              "Table 6 Surge Class")
    for cat, spec in g("BUILDING_CATEGORIES", {}).items():
        for k, v in spec.items():
            t.add("build.%s.%s" % (cat, k), v, "rule", 0, CFG_CLIMATE,
                  "BUILDING_CATEGORIES.%s.%s" % (cat, k), "literal",
                  "Table 6 Floors / Age / Function")
    for cls, v in g("KAPPA", {}).items():
        t.add("kappa.%s" % cls, float(v), "factor", 2, CFG_CLIMATE,
              "KAPPA.%s" % cls, "literal", "Table 6 last column")
    dd = g("SURGE_DEPTH_DAMAGE", {})
    for cls, spec in dd.items():
        for i, mdr in enumerate(spec["mdr"]):
            t.add("surge.dd.%s.d%d" % (cls, i), float(mdr), "MDR", 3,
                  CFG_CLIMATE, "SURGE_DEPTH_DAMAGE.%s.mdr[%d]" % (cls, i),
                  "literal", "Table 7 body")
    if dd:
        first = dd[sorted(dd)[0]]
        for i, dep in enumerate(first["depths"]):
            t.add("surge.depth.d%d" % i, float(dep), "m", 1, CFG_CLIMATE,
                  "SURGE_DEPTH_DAMAGE.depths[%d]" % i, "literal",
                  "Table 7 first column")
    for scen, (mult, shift) in g("CRI_SSP_DAMAGE_ADJ", {}).items():
        t.add("cri.ssp.%s.dmg_mult" % scen, float(mult), "factor", 2,
              CFG_CLIMATE, "CRI_SSP_DAMAGE_ADJ[%s][0]" % scen, "literal")
        t.add("cri.ssp.%s.sev_shift" % scen, float(shift), "log-shift", 3,
              CFG_CLIMATE, "CRI_SSP_DAMAGE_ADJ[%s][1]" % scen, "literal")
    for scen, v in g("CRI_SSP_H_DRIFT_MULT", {}).items():
        t.add("cri.ssp.%s.h_drift" % scen, float(v), "factor", 2, CFG_CLIMATE,
              "CRI_SSP_H_DRIFT_MULT[%s]" % scen, "literal")
    for nm in ("CFI_WEIGHT_PRECIP", "CFI_WEIGHT_WIND", "CFI_WEIGHT_HEAT",
               "CFI_WEIGHT_SLA"):
        t.add("cfi.%s" % nm, float(g(nm)), "weight", 2, CFG_CLIMATE, nm, "literal")
    for i, v in enumerate(g("CLIMATE_INDEX_COMPONENT_WEIGHTS", []).values()):
        t.add("cri.component_weight.%d" % i, float(v), "weight", 2, CFG_CLIMATE,
              "CLIMATE_INDEX_COMPONENT_WEIGHTS", "literal")
    if "FRI_WEIGHTS" in fin:
        for i, v in enumerate(fin["FRI_WEIGHTS"][0]):
            t.add("fweights.%d" % i, float(v), "weight", 6, CFG_FINANCE,
                  "FRI_WEIGHTS[%d]" % i, "literal", "Table B1 equal-weight baseline")
    else:
        # FRI_WEIGHTS is written as a tuple of fractions, not a literal
        src_fin = (NEWROOT / CFG_FINANCE).read_text(encoding="utf-8")
        m = re.search(r"FRI_WEIGHTS\s*=\s*\(([^)]*)\)", src_fin)
        if m:
            for i, term in enumerate(m.group(1).split(",")):
                try:
                    node = ast.parse(term.strip(), mode="eval").body
                    t.add("fweights.%d" % i, float(_safe_arith(node)),
                          "weight", 6, CFG_FINANCE, "FRI_WEIGHTS[%d]" % i,
                          "ast arithmetic on the source term")
                except (ValueError, SyntaxError, TypeError):
                    t.problems.append("FRI_WEIGHTS term %d unparsable" % i)
        else:
            t.problems.append("FRI_WEIGHTS not found")


def _safe_arith(node):
    """Evaluate a numeric sub-expression from a config file (no names, no calls)."""
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return -_safe_arith(node.operand)
    if isinstance(node, ast.BinOp):
        left, right = _safe_arith(node.left), _safe_arith(node.right)
        if isinstance(node.op, ast.Div):
            return left / right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
    raise TypeError("unsupported expression")


def add_source_constants(t: Truth) -> None:
    """Constants that live outside the three 00_config.py modules.

    They are still model parameters (and Table B1 quotes them), so they need a
    metric with a file:line origin just like the config literals.
    """
    # bounding box components
    clim = config_literals(CFG_CLIMATE)
    if "SHANGHAI_BBOX" in clim:
        box = clim["SHANGHAI_BBOX"][0]
        for name, v in zip(("west", "south", "east", "north"), box):
            t.add("bbox.%s" % name, float(v), "deg", 2, CFG_CLIMATE,
                  "SHANGHAI_BBOX", "tuple component", "Table B1 first row")

    # climate-CVaR module constants
    rel = r"Finance\01a_climate_cvar.py"
    src = (NEWROOT / rel).read_text(encoding="utf-8")
    for mid, pattern, digits, unit in (
        ("cvar.n_perturb", r"args\.test else (\d+)", 0, "count"),
        ("cvar.alpha", r"CVAR_ALPHA = ([0-9.]+)", 2, "quantile"),
        ("cvar.alpha_pct", r"CVAR_ALPHA = ([0-9.]+)", 0, "percent"),
        ("cvar.window_years", r"ROLLING_WINDOW_YEARS = (\d+)", 0, "years"),
    ):
        m = re.search(pattern, src)
        if m:
            val = float(m.group(1))
            if mid == "cvar.alpha_pct":
                val *= 100.0
            t.add(mid, val, unit, digits, rel,
                  "literal %r" % pattern, "regex on the module source")
        else:
            t.problems.append("constant not found: %s" % mid)

    # per-scenario jump-intensity multipliers (hard-coded inside main())
    rel2 = r"Finance\02_fri_projection.py"
    src2 = (NEWROOT / rel2).read_text(encoding="utf-8")
    block = re.search(r"scenario_lambda_mult\s*=\s*\{(.*?)\}", src2, re.S)
    if not block:
        t.problems.append("scenario_lambda_mult block not found")
        return
    pairs = dict(re.findall(r'"([^"]+)"\s*:\s*([0-9.]+)', block.group(1)))
    for scen in ("SSP2-4.5", "SSP5-8.5"):
        if scen in pairs:
            t.add("jump.mult.%s" % scen, float(pairs[scen]), "factor", 2, rel2,
                  "scenario_lambda_mult", "regex on the module source")
        else:
            t.problems.append("jump multiplier missing for %s" % scen)


# ─────────────────────────────────────────────────────────────────────────
# K : FRI jump-diffusion fit (Table B1 rows 63-68)
#
# These six numbers are *fitted* by Finance/02_fri_projection.py at run time and
# are never logged or persisted, so no artefact on disk records them.  To avoid
# either trusting the manuscript or re-implementing the fit (which would audit
# a copy instead of the pipeline), the fitting function itself is lifted out of
# the module with ast and executed here on the frozen F02 output columns
# `price` / `price_trend`.  Nothing is written and the module body never runs.
# ─────────────────────────────────────────────────────────────────────────

FRI_JUMP_METRICS = [
    ("theta_mr", "p.fit.theta_mr", "per month", 4, "HSI mean-reversion speed"),
    ("sigma_diff", "p.fit.sigma_diff", "per month", 5, "HSI diffusion volatility"),
    ("lambda_jump", "p.fit.lambda_jump", "per month", 5, "HSI jump intensity"),
    ("mu_jump", "p.fit.mu_jump", "log-return", 5, "HSI mean jump size"),
    ("sigma_jump", "p.fit.sigma_jump", "log-return", 5, "HSI jump-size volatility"),
    ("trend_growth", "p.fit.trend_growth", "per year", 5,
     "Recent HP trend growth for the projection anchor"),
]


def add_fri_fit(t: Truth) -> None:
    rel = r"Finance\02_fri_projection.py"
    src = (NEWROOT / rel).read_text(encoding="utf-8")
    tree = ast.parse(src)
    fns = [n for n in tree.body
           if isinstance(n, ast.FunctionDef) and n.name == "fit_jump_diffusion"]
    if not fns:
        t.problems.append("fit_jump_diffusion not found in %s" % rel)
        return
    try:
        import numpy as np
    except Exception as exc:                                  # pragma: no cover
        t.problems.append("numpy unavailable (%s): FRI fit not re-derived" % exc)
        return
    ns = {"np": np, "__name__": "wp11_fit"}
    try:
        exec(compile(ast.Module(body=fns, type_ignores=[]), rel, "exec"), ns)
        rows = read_rows(SRC_HSI)
        prices = np.asarray([float(r["price"]) for r in rows
                             if r["price"].strip() not in ("", "nan")])
        trend = np.asarray([float(r["price_trend"]) for r in rows
                            if r["price_trend"].strip() not in ("", "nan")])
        jd = ns["fit_jump_diffusion"](prices, trend)
    except Exception as exc:
        t.problems.append("FRI jump-diffusion fit failed: %r" % (exc,))
        return
    for key, mid, unit, digits, label in FRI_JUMP_METRICS:
        if key not in jd:
            t.problems.append("fit result missing key %s" % key)
            continue
        t.add(mid, float(jd[key]), unit, digits, rel,
              "fit_jump_diffusion(%d months of price/price_trend)" % len(prices),
              "re-executed from the pipeline source via ast", label)


# ─────────────────────────────────────────────────────────────────────────
# L : boundary geometry and raster-derived data facts
# ─────────────────────────────────────────────────────────────────────────

SRC_EAL_LEGACY = (r"output_archive\baseline_legacy_20261016_212711"
                  r"\Climate\output\results\defense_sensitivity"
                  r"\defense_profile_eal.csv")
SHP_OFFICIAL = (r"data\我国乡镇（街道）行政区划数据\_官方_天地图GS2024-0650"
                r"\上海_区级_GS2024-0650.shp")
ELEV_NPY = r"Climate\output\intermediate\building_elevation.npy"
COAST_NPY = r"Climate\output\intermediate\building_coast_distance_m.npy"


def add_boundary(t: Truth) -> None:
    # (1) union area of the official district layer, recomputed in EPSG:32651
    try:
        import geopandas as gpd
        gdf = gpd.read_file(str(NEWROOT / SHP_OFFICIAL))
        area = float(gdf.to_crs("EPSG:32651").geometry.union_all().area) / 1e6
        t.add("boundary.union_area_km2", area, "km2", 3, SHP_OFFICIAL,
              "%d polygons" % len(gdf), "union().area in EPSG:32651 / 1e6",
              "the 'approximately 7,205 km2' of the Data section")
        t.add("boundary.n_polygons", len(gdf), "count", 0, SHP_OFFICIAL,
              "features", "len(gdf)", "the 16 district polygons")
    except Exception as exc:
        t.problems.append("official boundary area not recomputed: %r" % (exc,))

    # (2) residual surge offset of the coastline decoupling: max |A - legacy|
    #     over the six scenario x defence-profile city cells.  The legacy run is
    #     the pre-2026-10 baseline (old township layer + its own shoreline), so
    #     the figure bundles both boundary and shoreline change - that is the
    #     "+0.21% residual offset" the Data section reports.
    try:
        a = read_rows(SRC_EAL)

        def cells(rows):
            out = {}
            for scen in ("historical", "SSP2-4.5", "SSP5-8.5"):
                for prof in ("baseline_nodef", "current_def_gap"):
                    out[(scen, prof)] = sum(
                        fnum(r, "EAL_compound") for r in rows
                        if r["scenario"] == scen and r["defense_profile"] == prof)
            return out

        ca = cells(a)
        cl = cells(read_rows(SRC_EAL_LEGACY))
        worst = max(abs(ca[k] / cl[k] - 1.0) * 100.0 for k in ca)
        t.add("boundary.residual_offset_max_pct", worst, "%", 4,
              SRC_EAL_LEGACY, "6 scenario x profile city cells",
              "max|A/legacy - 1|*100",
              "the '+0.21%' of the Data section")
        t.add("boundary.hist_nodef_vs_legacy_pct",
              (ca[("historical", "baseline_nodef")]
               / cl[("historical", "baseline_nodef")] - 1.0) * 100.0, "%", 4,
              SRC_EAL_LEGACY, "historical / baseline_nodef",
              "A/legacy - 1", "the single cell behind the headline offset")
    except Exception as exc:
        t.problems.append("residual surge offset not recomputed: %r" % (exc,))


def add_data_raster(t: Truth) -> None:
    try:
        import numpy as np
    except Exception as exc:                                  # pragma: no cover
        t.problems.append("numpy unavailable (%s): rasters not read" % exc)
        return
    p = NEWROOT / ELEV_NPY
    if p.is_file():
        a = np.load(str(p))
        t.add("data.n_buildings_npy", int(a.size), "count", 0, ELEV_NPY,
              "array length", "a.size", "cross-check of the 585,033 buildings")
        t.add("data.elev_mean", float(np.nanmean(a)), "m", 2, ELEV_NPY,
              "nanmean", "mean(building_elevation)")
        t.add("data.elev_median", float(np.nanmedian(a)), "m", 2, ELEV_NPY,
              "nanmedian", "median(building_elevation)",
              "the 'median building site' of the Introduction")
        t.add("data.elev_share_le3_pct", float(np.nanmean(a <= 3.0)) * 100.0,
              "%", 1, ELEV_NPY, "share(a <= 3 m)", "mean(a<=3)*100")
    q = NEWROOT / COAST_NPY
    if q.is_file():
        c = np.load(str(q))
        t.add("data.coast_dist_mean", float(np.nanmean(c)), "m", 0, COAST_NPY,
              "nanmean", "mean(building_coast_distance_m)")
        t.add("data.coast_dist_max", float(np.nanmax(c)), "m", 0, COAST_NPY,
              "nanmax", "max(building_coast_distance_m)")


# ─────────────────────────────────────────────────────────────────────────
# main
# ─────────────────────────────────────────────────────────────────────────


def check_baseline(t: Truth) -> None:
    if not BASELINE.is_file():
        t.problems.append("baseline missing: %s (run _wp11_freeze.py)" % BASELINE)
        return
    base = json.loads(BASELINE.read_text(encoding="utf-8"))
    want: dict[str, str] = {}
    for role in base["roles"].values():
        for rel, v in role.items():
            if "sha256" in v:
                want[rel] = v["sha256"]
    checked = 0
    for rel, sha in sorted(want.items()):
        p = NEWROOT / rel
        if not p.is_file():
            t.problems.append("source vanished: %s" % rel)
            continue
        if sha256(p) != sha:
            t.problems.append("source CHANGED since freeze: %s" % rel)
        checked += 1
    print("  baseline: %d source files verified" % checked)


def main() -> int:
    ap = argparse.ArgumentParser(description="WP11.1 canonical truth engine")
    ap.add_argument("--out", default=str(OUT_CSV))
    ap.add_argument("--no-baseline", action="store_true")
    ap.add_argument("--show", default="")
    args = ap.parse_args()

    t = Truth()
    print("=== WP11.1 canonical truth engine ===")
    if not args.no_baseline:
        check_baseline(t)

    add_eal(t)
    add_cri(t)
    add_hsi(t)
    add_cchi(t)
    add_dependence(t)
    add_table8(t)
    add_params(t)
    add_derived_params(t)
    add_source_constants(t)
    add_logfacts(t)
    add_fri_fit(t)
    add_boundary(t)
    add_data_raster(t)
    add_exposure_constants(t)
    add_misc_facts(t)
    add_data_windows(t)

    if args.show:
        print("  --- metrics matching %r ---" % args.show)
        for r in t.rows:
            if args.show in r["metric_id"]:
                print("  %-44s %-18s %s" % (r["metric_id"], r["value"], r["unit"]))

    print("  metrics: %d" % len(t.rows))
    print("  problems: %d" % len(t.problems))
    for p in t.problems[:20]:
        print("    ! " + p)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    cols = ["metric_id", "value", "unit", "digits", "source", "locator",
            "formula", "note"]
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=cols, lineterminator="\n")
    w.writeheader()
    for r in t.rows:
        w.writerow(r)
    tmp = out.with_suffix(".csv.tmp")
    tmp.write_text(buf.getvalue(), encoding="utf-8", newline="\n")
    tmp.replace(out)
    print("  wrote %s (%d rows)" % (out.relative_to(NEWROOT), len(t.rows)))

    if t.problems:
        print("RESULT: TRUTH-INCOMPLETE")
        return 1
    print("RESULT: TRUTH-OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
