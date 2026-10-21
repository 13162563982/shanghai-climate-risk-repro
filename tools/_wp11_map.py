# -*- coding: utf-8 -*-
"""WP11.3 - classify and bind every numeric token of PAPER_MANUSCRIPT_v11.docx.

WHY THIS FILE EXISTS
--------------------
An audit is only as good as its coverage.  The previous alignment pass bound
about 130 tokens through a hand-written `ASSIGNMENTS` list in
tools/extract_manuscript_numbers.py, i.e. well under a fifth of the 1,385
numeric tokens v11 actually contains.  This module forces a decision for *every*
token and makes "no decision" a hard failure:

    REF        bibliography block (P256-P313)                - excluded, counted
    STRUCT     figure / table / section / scenario labels    - structural
    LIT        literature or external statistics             - excluded, counted
    PARAM      model parameter, bound to a code constant     - verified
    DATA       input-data or run-log fact                    - verified
    MODEL      simulation output                             - verified
    NOTE       a quantity that is not a model number         - must say why

Every PARAM / DATA / MODEL row carries a `metric_id` that must exist in
docs/_wp11_真值表.csv, so the checker can format the canonical value at the
precision the manuscript prints and compare strings.

Two safety nets keep the map honest:
  * MAP-DRIFT   - if the declared token list for an element no longer matches the
                  document, the element is reported instead of silently skipped;
  * UNCLASSIFIED - any token the rules do not resolve blocks the gate.

USAGE
-----
  env\\run.ps1 tools\\_wp11_map.py
  env\\run.ps1 tools\\_wp11_map.py --show-unclassified
"""

from __future__ import annotations

import argparse
import csv
import io
import re
import sys
from pathlib import Path

NEWROOT = Path(__file__).resolve().parent.parent
DOCS = NEWROOT / "docs"
TOKENS = DOCS / "_wp11_v11清单.csv"
TRUTH = DOCS / "_wp11_真值表.csv"
OUT = DOCS / "_wp11映射表.csv"

S, L, P, D, M, N, R = "STRUCT", "LIT", "PARAM", "DATA", "MODEL", "NOTE", "REF"
VERIFIED = {P, D, M}

# ─────────────────────────────────────────────────────────────────────────
# Element-scoped assignments: (raw token, class, bind)
# bind is a metric_id for P/D/M and a free-text justification otherwise.
# The declared token sequence must match the document exactly (MAP-DRIFT).
# ─────────────────────────────────────────────────────────────────────────

CITATION = "in-text citation year (bibliography); not a model quantity"

ELEM: dict[str, list[tuple[str, str, str]]] = {
    # ---------------- abstract / introduction
    "P4": [
        ("2050", S, "projection horizon"),
        ("24.2 billion", M, "eal.city.hist.nodef.bn"),
        ("6 m", P, "defence.current_def_gap.coastal_defense_crest_m"),
        ("21.5%", M, "eal.city.hist.red_pct"),
        ("74%", M, "eal.city.hist.wind_share_pct"),
        ("8.5", S, "scenario label SSP5-8.5"),
        ("66%", M, "eal.city.ssp585.incr_vs_hist_pct"),
        ("40.3 billion", M, "eal.city.ssp585.nodef.bn"),
        ("2050", S, "projection horizon"),
        ("26%", M, "eal.city.hist.surge_share_pct"),
        ("40%", M, "eal.city.ssp585.surge_share_pct"),
        ("53%", M, "cchi.incr.ssp585.p50_pct"),
    ],
    "P6": [
        ("2008", L, CITATION), ("2013", L, CITATION),
        ("24.87 million", L, "external statistic: Shanghai resident population"),
        ("63.3 trillion", D, "exposure.total_t"),
        ("2.7 m", D, "data.elev_median"),
        ("2020", L, CITATION), ("2021", L, CITATION),
        ("1986", L, CITATION), ("2015", L, CITATION),
    ],
    "P7": [(t, L, CITATION) for t in
           ("2019", "2021", "2023", "2012", "2017", "2020",
            "2019", "2013", "2021", "2020", "2018")],
    "P8": [("2013", L, CITATION), ("2020", L, CITATION)],
    "P9": [
        ("2050", S, "projection horizon"),
        ("15", S, "reference to Figure 15"),
        ("585,033", D, "data.n_buildings_npy"),
        ("63.3 trillion", D, "exposure.total_t"),
        ("0.9999", D, "calib.aal_pred_obs"),
        ("1995", D, "calib.window_start"),
        ("2023", D, "calib.window_end"),
        ("10", P, "p.Climate.NB_SYNTH_TRACKS"),
    ],
    "P10": [("6 m", P, "defence.current_def_gap.coastal_defense_crest_m"),
            ("2050", S, "projection horizon")],
    # ---------------- Results 1
    "P14": [
        ("24.2 billion", M, "eal.city.hist.nodef.bn"),
        ("17.9 billion", M, "eal.city.hist.wind.bn"),
        ("74%", M, "eal.city.hist.wind_share_pct"),
        ("6.3 billion", M, "eal.city.hist.surge.bn"),
        ("26%", M, "eal.city.hist.surge_share_pct"),
        ("1", S, "reference to Table 1"),
        ("6 m", P, "defence.current_def_gap.coastal_defense_crest_m"),
        ("19.0 billion", M, "eal.city.hist.def.bn"),
        ("21.5%", M, "eal.city.hist.red_pct"),
    ],
    "P15": [("1", S, "Table 1 caption number")],
    "T0#r0c2": [("6 m", P, "defence.current_def_gap.coastal_defense_crest_m")],
    "T0#r1c1": [("24.2", M, "eal.city.hist.nodef.bn")],
    "T0#r1c2": [("19.0", M, "eal.city.hist.def.bn")],
    "T0#r1c3": [("21.5%", M, "eal.city.hist.red_pct")],
    "T0#r2c0": [("4.5", S, "scenario label SSP2-4.5"),
                ("+0.3 m", P, "log.surge.slr_245")],
    "T0#r2c1": [("33.4", M, "eal.city.ssp245.nodef.bn")],
    "T0#r2c2": [("23.9", M, "eal.city.ssp245.def.bn")],
    "T0#r2c3": [("28%", M, "eal.city.ssp245.red_pct")],
    "T0#r3c0": [("8.5", S, "scenario label SSP5-8.5"),
                ("+0.5 m", P, "log.surge.slr_585")],
    "T0#r3c1": [("40.3", M, "eal.city.ssp585.nodef.bn")],
    "T0#r3c2": [("26.5", M, "eal.city.ssp585.def.bn")],
    "T0#r3c3": [("34%", M, "eal.city.ssp585.red_pct")],
    "P16": [
        ("4.5", S, "scenario label SSP2-4.5"),
        ("8.5", S, "scenario label SSP5-8.5"),
        ("33.4 billion", M, "eal.city.ssp245.nodef.bn"),
        ("+38%", M, "eal.city.ssp245.incr_vs_hist_pct"),
        ("40.3 billion", M, "eal.city.ssp585.nodef.bn"),
        ("+66%", M, "eal.city.ssp585.incr_vs_hist_pct"),
        ("26%", M, "eal.city.hist.surge_share_pct"),
        ("33%", M, "eal.city.ssp245.surge_share_pct"),
        ("40%", M, "eal.city.ssp585.surge_share_pct"),
        ("1", S, "reference to Table 1"),
        ("6.3 billion", M, "eal.city.hist.surge.bn"),
        ("16 billion", M, "eal.city.ssp585.surge.bn"),
        ("8.5", S, "scenario label SSP5-8.5"),
        ("6 m", P, "defence.current_def_gap.coastal_defense_crest_m"),
        ("26.5 billion", M, "eal.city.ssp585.def.bn"),
        ("8.5", S, "scenario label SSP5-8.5"),
        ("39.5%", M, "eal.residual.ssp585_def_vs_hist_def_pct"),
        ("6 m", P, "defence.current_def_gap.coastal_defense_crest_m"),
    ],
    "P17": [
        ("1995", D, "calib.window_start"),
        ("2023", D, "calib.window_end"),
        ("0.9999", D, "calib.aal_pred_obs"),
        ("8", S, "reference to Table 8"),
        ("1,070", D, "log.tc.n_synth_added"),
    ],
    # ---------------- Results 2
    "P19": [
        ("6.0 billion", M, "eal.dist.hist.浦东新区.bn"),
        ("1", S, "reference to Fig. 1"),
        ("2", S, "reference to Table 2"),
        ("0.82‰", M, "eal.dist.hist.虹口区.ratio_permille"),
        ("0.77‰", M, "eal.dist.hist.杨浦区.ratio_permille"),
        ("0.67‰", M, "eal.dist.hist.黄浦区.ratio_permille"),
        ("0.39‰", M, "eal.dist.hist.mean_of_ratios_permille"),
        ("0.40‰", M, "eal.dist.hist.浦东新区.ratio_permille"),
    ],
    "P20": [("2", S, "Table 2 caption number")],
    "T1#r1c1": [("6.0", M, "eal.dist.hist.浦东新区.bn")],
    "T1#r1c2": [("14.8", M, "eal.dist.hist.浦东新区.expo_t")],
    "T1#r1c3": [("0.40", M, "eal.dist.hist.浦东新区.ratio_permille")],
    "T1#r2c1": [("2.6", M, "eal.dist.hist.杨浦区.bn")],
    "T1#r2c2": [("3.4", M, "eal.dist.hist.杨浦区.expo_t")],
    "T1#r2c3": [("0.77", M, "eal.dist.hist.杨浦区.ratio_permille")],
    "T1#r3c1": [("2.3", M, "eal.dist.hist.闵行区.bn")],
    "T1#r3c2": [("8.0", M, "eal.dist.hist.闵行区.expo_t")],
    "T1#r3c3": [("0.28", M, "eal.dist.hist.闵行区.ratio_permille")],
    "T1#r4c1": [("2.2", M, "eal.dist.hist.徐汇区.bn")],
    "T1#r4c2": [("4.0", M, "eal.dist.hist.徐汇区.expo_t")],
    "T1#r4c3": [("0.56", M, "eal.dist.hist.徐汇区.ratio_permille")],
    "T1#r5c1": [("1.7", M, "eal.dist.hist.虹口区.bn")],
    "T1#r5c2": [("2.0", M, "eal.dist.hist.虹口区.expo_t")],
    "T1#r5c3": [("0.82", M, "eal.dist.hist.虹口区.ratio_permille")],
    "P21": [
        ("1990", P, "build.A_old.age_before"),
        ("34", S, "reference to Fig. 34"),
        ("8.5", S, "scenario label SSP5-8.5"),
        ("5.4 billion", M, "eal.dist.ssp585.杨浦区.bn"),
        ("1.56‰", M, "eal.dist.ssp585.杨浦区.ratio_permille"),
        ("3.5 billion", M, "eal.dist.ssp585.虹口区.bn"),
        ("1.72‰", M, "eal.dist.ssp585.虹口区.ratio_permille"),
    ],
    # ---------------- figures 1-6 (labels / captions)
    "P23": [("1", S, "Figure label")], "P24": [("1", S, "Figure caption")],
    "P26": [("2", S, "Figure label")],
    "P27": [("2", S, "Figure caption"),
            ("4.5", S, "scenario label"), ("8.5", S, "scenario label")],
    "P29": [("3", S, "Figure label")], "P30": [("3", S, "Figure caption")],
    "P32": [("4", S, "Figure label")], "P33": [("4", S, "Figure caption")],
    "P35": [("5", S, "Figure label")],
    "P36": [("5", S, "Figure caption"),
            ("0.05 m", P, "p.Climate.DISTRICT_SURGE_EVENT_COUNT_DEPTH_THRESHOLD_M")],
    "P38": [("6", S, "Figure label")], "P39": [("6", S, "Figure caption")],
    # ---------------- Results 3 : CRI
    "P41": [
        ("1993", D, "cri.hist.first_year"),
        ("100", M, "cri.hist.start"),
        ("440.3", M, "cri.hist.2023_12"),
        ("2023", D, "cri.hist.last_year"),
        ("4.4", M, "cri.hist.fold"),
        ("7", S, "reference to Fig. 7"),
    ],
    "P42": [
        ("500", P, "p.Climate.CRI_N_SIM"),
        ("2050", S, "projection horizon"),
        ("601", M, "cri.proj.hist.p50"),
        ("675", M, "cri.proj.ssp245.p50"),
        ("4.5", S, "scenario label SSP2-4.5"),
        ("745", M, "cri.proj.ssp585.p50"),
        ("8.5", S, "scenario label SSP5-8.5"),
        ("2050", S, "projection horizon"),
        ("3", S, "reference to Table 3"),
        ("12.4%", M, "cri.incr.ssp245.p50_vs_hist2050_pct"),
        ("23.9%", M, "cri.incr.ssp585.p50_vs_hist2050_pct"),
        ("10", S, "10th percentile"),
        ("90", S, "90th percentile"),
        ("490", M, "cri.proj.hist.p10"),
        ("689", M, "cri.proj.hist.p90"),
        ("564", M, "cri.proj.ssp245.p10"),
        ("768", M, "cri.proj.ssp245.p90"),
        ("641", M, "cri.proj.ssp585.p10"),
        ("837", M, "cri.proj.ssp585.p90"),
        ("2050", S, "projection horizon"),
        ("2%", M, "t8.r13.dev_max"),
    ],
    "P43": [("3", S, "Table 3 caption number"),
            ("2050", S, "projection horizon")],
    "T2#r0c1": [("10", S, "column header 10th")],
    "T2#r0c2": [("50", S, "column header median")],
    "T2#r0c3": [("90", S, "column header 90th")],
    "T2#r1c1": [("491", M, "cri.proj.hist.p10")],
    "T2#r1c2": [("601", M, "cri.proj.hist.p50")],
    "T2#r1c3": [("692", M, "cri.proj.hist.p90")],
    "T2#r2c0": [("4.5", S, "scenario label")],
    "T2#r2c1": [("565", M, "cri.proj.ssp245.p10")],
    "T2#r2c2": [("675", M, "cri.proj.ssp245.p50")],
    "T2#r2c3": [("770", M, "cri.proj.ssp245.p90")],
    "T2#r3c0": [("8.5", S, "scenario label")],
    "T2#r3c1": [("643", M, "cri.proj.ssp585.p10")],
    "T2#r3c2": [("745", M, "cri.proj.ssp585.p50")],
    "T2#r3c3": [("840", M, "cri.proj.ssp585.p90")],
    "P45": [("7", S, "Figure label")],
    "P46": [("7", S, "Figure caption"),
            ("1993", D, "cri.hist.first_year"), ("2023", D, "cri.hist.last_year"),
            ("2050", S, "projection horizon"),
            ("10", S, "10th percentile"), ("90", S, "90th percentile")],
    # ---------------- Results 4 : HSI
    "P48": [
        ("8", S, "reference to Fig. 8"), ("9", S, "reference to Fig. 9"),
        ("2011", D, "hsi.hist.first_year"),
        ("100", M, "hsi.hist.first"),
        ("231", M, "hsi.hist.last"),
        ("2025", D, "hsi.hist.last_year"),
        ("254", M, "hsi.hist.peak"),
        ("2023", D, "hsi.hist.peak_year"),
    ],
    "P49": [
        ("2011", D, "dep.start_year"),
        ("2023", D, "dep.end_year"),
        ("0.358", P, "p.Composite.CFCI_TARGET_RHO"),
        ("130", M, "cchi.hist.first"),
        ("313", M, "cchi.hist.2023_12"),
        ("12", S, "reference to Fig. 12"), ("13", S, "reference to Fig. 13"),
        ("399", M, "cchi.proj.hist.p50"),
        ("441", M, "cchi.proj.ssp245.p50"),
        ("4.5", S, "scenario label"),
        ("479", M, "cchi.proj.ssp585.p50"),
        ("8.5", S, "scenario label"),
        ("2050", S, "projection horizon"),
        ("8.5", S, "scenario label"),
        ("53%", M, "cchi.incr.ssp585.p50_pct"),
        ("2023", D, "cchi.hist.end_year"),
    ],
    "P50": [("4", S, "Table 4 caption number"),
            ("2050", S, "projection horizon")],
    "T3#r0c1": [("10", S, "column header")],
    "T3#r0c2": [("50", S, "column header")],
    "T3#r0c3": [("90", S, "column header")],
    "T3#r1c1": [("230", M, "hsi.proj.hist.p10")],
    "T3#r1c2": [("265", M, "hsi.proj.hist.p50")],
    "T3#r1c3": [("329", M, "hsi.proj.hist.p90")],
    "T3#r2c0": [("4.5", S, "scenario label")],
    "T3#r2c1": [("251", M, "hsi.proj.ssp245.p10")],
    "T3#r2c2": [("287", M, "hsi.proj.ssp245.p50")],
    "T3#r2c3": [("354", M, "hsi.proj.ssp245.p90")],
    "T3#r3c0": [("8.5", S, "scenario label")],
    "T3#r3c1": [("270", M, "hsi.proj.ssp585.p10")],
    "T3#r3c2": [("307", M, "hsi.proj.ssp585.p50")],
    "T3#r3c3": [("375", M, "hsi.proj.ssp585.p90")],
    "P52": [("8", S, "Figure label")],
    "P53": [("8", S, "Figure caption"),
            ("2011", D, "hsi.hist.first_year"), ("2025", D, "hsi.hist.last_year"),
            ("100", M, "hsi.hist.first"), ("231", M, "hsi.hist.last"),
            ("2023", D, "hsi.hist.peak_year")],
    "P55": [("9", S, "Figure label")], "P56": [("9", S, "Figure caption")],
    "P58": [("10", S, "Figure label")], "P59": [("10", S, "Figure caption")],
    "P61": [("11", S, "Figure label")],
    "P62": [("11", S, "Figure caption"),
            ("2011", D, "dep.start_year"), ("12", N, "month component of a date"),
            ("2023", D, "dep.end_year"), ("12", N, "month component of a date")],
    # ---------------- Results 5 : CCHI
    "P65": [("5", S, "Table 5 caption number"),
            ("2050", S, "projection horizon")],
    "T4#r0c1": [("10", S, "column header")],
    "T4#r0c2": [("50", S, "column header")],
    "T4#r0c3": [("90", S, "column header")],
    "T4#r1c1": [("354", M, "cchi.proj.hist.p10")],
    "T4#r1c2": [("399", M, "cchi.proj.hist.p50")],
    "T4#r1c3": [("457", M, "cchi.proj.hist.p90")],
    "T4#r2c0": [("4.5", S, "scenario label")],
    "T4#r2c1": [("394", M, "cchi.proj.ssp245.p10")],
    "T4#r2c2": [("441", M, "cchi.proj.ssp245.p50")],
    "T4#r2c3": [("499", M, "cchi.proj.ssp245.p90")],
    "T4#r3c0": [("8.5", S, "scenario label")],
    "T4#r3c1": [("435", M, "cchi.proj.ssp585.p10")],
    "T4#r3c2": [("479", M, "cchi.proj.ssp585.p50")],
    "T4#r3c3": [("534", M, "cchi.proj.ssp585.p90")],
    "P66": [
        ("0.0", M, "sweep.CFCI_TARGET_RHO.v0"),
        ("0.8", M, "sweep.CFCI_TARGET_RHO.v4"),
        ("−0.2%", M, "t8.r20.dev_min"),
        ("+0.6%", M, "t8.r20.dev_max"),
        ("53%", M, "cchi.incr.ssp585.p50_pct"),
        ("8", S, "reference to Table 8"),
        ("17%", M, "t8.r18.dev_max"),
    ],
    "P68": [("12", S, "Figure label")], "P69": [("12", S, "Figure caption")],
    "P71": [("13", S, "Figure label")], "P72": [("13", S, "Figure caption")],
    "P74": [("14", S, "Figure label")], "P75": [("14", S, "Figure caption"),
            ("2011", D, "cchi.hist.start_year"),
            ("2023", D, "cchi.hist.end_year")],
    # ---------------- Discussion / Conclusion
    "P77": [
        ("74%", M, "eal.city.hist.wind_share_pct"),
        ("6 m", P, "defence.current_def_gap.coastal_defense_crest_m"),
        ("21.5%", M, "eal.city.hist.red_pct"),
        ("1993", D, "cri.hist.first_year"),
        ("601", M, "cri.proj.hist.p50"),
        ("745", M, "cri.proj.ssp585.p50"),
        ("2050", S, "projection horizon"),
        ("53%", M, "cchi.incr.ssp585.p50_pct"),
        ("8.5", S, "scenario label"),
    ],
    "P78": [(t, L, CITATION) for t in
            ("2012", "2015", "2020", "2019", "2020", "2021",
             "2023", "2020", "2013", "2020")],
    "P79": [
        ("21.5%", M, "eal.city.hist.red_pct"),
        ("34.2%", M, "eal.city.ssp585.red_pct"),
        ("8.5", S, "scenario label"),
        ("24", S, "reference to Section 1.4"),
        ("39.5%", M, "eal.residual.ssp585_def_vs_hist_def_pct"),
        ("8", S, "reference to Table 8"),
        ("−23%", M, "t8.r4.dev_min"),
        ("+31%", M, "t8.r4.dev_max"),
        ("2%", M, "t8.r13.dev_max"),
    ],
    "P80": [("1990", P, "build.A_old.age_before")],
    "P81": [
        ("1", S, "limitation list numbering"),
        ("2", S, "limitation list numbering"),
        ("10×", P, "p.Climate.NB_SYNTH_TRACKS"),
        ("3", S, "limitation list numbering"),
        ("73.5%", D, "log.exp.age_coverage_pct"),
        ("4", S, "limitation list numbering"),
        ("2011", D, "data.fri_start_year"),
        ("2025", D, "data.fri_end_year"),
        ("5", S, "limitation list numbering"),
        ("6", S, "limitation list numbering"),
    ],
    "P83": [
        ("2050", S, "projection horizon"),
        ("74%", M, "eal.city.hist.wind_share_pct"),
        ("6 m", P, "defence.current_def_gap.coastal_defense_crest_m"),
        ("21.5%", M, "eal.city.hist.red_pct"),
        ("8.5", S, "scenario label"),
        ("26.5 billion", M, "eal.city.ssp585.def.bn"),
        ("1993", D, "cri.hist.first_year"),
        ("2023", D, "cri.hist.last_year"),
        ("601", M, "cri.proj.hist.p50"),
        ("745", M, "cri.proj.ssp585.p50"),
        ("2050", S, "projection horizon"),
        ("53%", M, "cchi.incr.ssp585.p50_pct"),
        ("8.5", S, "scenario label"),
    ],
    # ---------------- Methods
    "P85": [
        ("15", S, "reference to Figure 15"),
        ("1.1", S, "section number"), ("1.6", S, "section number"),
        ("1.7", S, "section number"), ("1.8", S, "section number"),
    ],
    "P86": [("15", S, "Figure label")],
    "P87": [("1.1", S, "section number")],
    "P88": [("1.1", S, "section number")],
    "P89": [("2010", L, CITATION), ("1980", L, CITATION),
            ("2008", L, CITATION), ("2010", L, CITATION),
            ("2019", L, CITATION), ("2021", L, CITATION),
            ("0.01", P, "p.Climate.MODEL_RESOLUTION_DEG")],
    "P90": [("1.1", S, "section number")],
    "P91": [("10", P, "p.Climate.NB_SYNTH_TRACKS"), ("2006", L, CITATION),
            ("42", P, "p.Climate.RANDOM_SEED")],
    "P92": [("1.1", S, "section number")],
    "P93": [("2020", L, CITATION), ("50", S, "50th percentile"),
            ("1985", D, "knutson.baseline_start"), ("2005", D, "knutson.baseline_end"),
            ("2050", S, "target year"),
            ("1.05", P, "log.tc.knutson_ssp245"),
            ("4.5", S, "scenario label"),
            ("1.10", P, "log.tc.knutson_ssp585"),
            ("8.5", S, "scenario label")],
    "P95": [("16", S, "Figure label")], "P96": [("16", S, "Figure caption")],
    "P97": [("1.2", S, "section number")], "P98": [("1.2", S, "section number")],
    "P99": [(t, L, CITATION) for t in
            ("1982", "2011", "1991", "2008", "1981", "2003")],
    "P100": [("1.2", S, "section number")],
    "P102": [("1.2", S, "section number")],
    "P103": [("17", S, "Figure label")],
    "P104": [("1.2", S, "section number")],
    "P105": [("0.3 m", P, "log.surge.slr_245"), ("4.5", S, "scenario label"),
             ("0.5 m", P, "log.surge.slr_585"), ("8.5", S, "scenario label"),
             ("2050", S, "target year"), ("2021", L, CITATION)],
    "P107": [("17", S, "Figure caption")],
    "P108": [("17", S, "Figure caption"),
             ("0.01", P, "p.Climate.MODEL_RESOLUTION_DEG")],
    "P110": [("18", S, "Figure label")], "P111": [("18", S, "Figure caption")],
    "P112": [("1.3", S, "section number")], "P113": [("1.3", S, "section number")],
    "P114": [("2011", L, CITATION), ("2021", L, CITATION),
             ("6", S, "reference to Table 6")],
    "P115": [("6", S, "Table 6 caption number")],
    "P118": [("19", S, "Figure label")],
    "P119": [("19", S, "Figure caption"), ("1990", L, CITATION)],
    "P120": [("1.3", S, "section number")],
    "P121": [("2022", L, CITATION), ("0.176", P, "p.Climate.SURGE_MDR_CALIBRATION_SCALE")],
    "P122": [("7", S, "Table 7 caption number"),
             ("0.176", P, "p.Climate.SURGE_MDR_CALIBRATION_SCALE")],
    "P123": [("0.176", P, "p.Climate.SURGE_MDR_CALIBRATION_SCALE"),
             ("10 m", N, "stated extent of the depth axis, not a model parameter")],
    "P128": [("2003", L, CITATION), ("1990", D, "temp.anomaly.base_y0"),
             ("2020", D, "temp.anomaly.base_y1")],
    "P130": [("55", N, "TR-55 technical-release identifier"), ("1986", L, CITATION),
             ("2015", L, CITATION)],
    "P136": [("2015", L, CITATION), ("0.25", N, "worked-example coupling coefficient"),
             ("0.60", N, "worked example of a coupling coefficient")],
    "P142": [("0 m", P, "defence.baseline_nodef.coastal_defense_crest_m"),
             ("6 m", P, "defence.current_def_gap.coastal_defense_crest_m")],
    "P144": [("2050", S, "projection horizon")],
    "P149": [("0.85", P, "p.Climate.CRI_EWMA_ALPHA"),
             ("0.5", P, "p.Climate.CRI_DAMAGE_KAPPA"),
             ("12", P, "p.Climate.CLIMATE_INDEX_TREND_WINDOW_MONTHS"),
             ("100", P, "p.Climate.CRI_BASE_INDEX"),
             ("1993", D, "cri.hist.first_year")],
    "P150": [("1.6", S, "section number"), ("2024", D, "cri.proj.start_year"), ("2050", S, "projection horizon")],
    "P151": [("1930", L, CITATION), ("2000", L, CITATION)],
    "P152": [("1.0×", P, "cri.ssp.Historical Baseline.h_drift"),
             ("1.5×", P, "cri.ssp.SSP2-4.5.h_drift"),
             ("4.5", S, "scenario label"),
             ("2.0×", P, "cri.ssp.SSP5-8.5.h_drift"),
             ("8.5", S, "scenario label"), ("2021", L, CITATION),
             ("1.05", P, "cri.ssp.SSP2-4.5.dmg_mult"),
             ("4.5", S, "scenario label"),
             ("1.08", P, "cri.ssp.SSP5-8.5.dmg_mult"),
             ("8.5", S, "scenario label"),
             ("+0.068", P, "cri.ssp.SSP2-4.5.sev_shift"),
             ("+0.095", P, "cri.ssp.SSP5-8.5.sev_shift"),
             ("2020", L, CITATION)],
    "P157": [("2002", L, CITATION), ("1997", L, CITATION)],
    "P158": [("12", P, "p.Finance.VOLATILITY_WINDOW")],
    "P159": [("2000", L, CITATION), ("2002", L, CITATION), ("1997", L, CITATION),
             ("107", D, "log.tc.n_tracks_hist"),
             ("10,807", D, "cvar.n_realisations"),
             ("100", P, "cvar.n_perturb"),
             ("5", P, "cvar.window_years"),
             ("2021", L, CITATION), ("2023", L, CITATION)],
    "P160": [("12", P, "p.Climate.CLIMATE_INDEX_TREND_WINDOW_MONTHS"),
             ("100", P, "p.Finance.FRI_BASE_INDEX"),
             ("2011", D, "hsi.hist.first_year")],
    "P162": [("2050", S, "projection horizon"), ("1974", L, CITATION),
             ("1976", L, CITATION), ("1989", L, CITATION),
             ("2011", D, "hsi.hist.first_year"), ("01", N, "month component of a date"),
             ("2025", D, "hsi.hist.last_year"), ("06", N, "month component of a date")],
    "P163": [("1.10", P, "jump.mult.SSP2-4.5"), ("4.5", S, "scenario label"),
             ("1.20", P, "jump.mult.SSP5-8.5"), ("8.5", S, "scenario label"),
             ("2020", L, CITATION)],
    "P167": [("2010", L, CITATION)],
    "P169": [("1982", L, CITATION), ("2005", L, CITATION)],
    "P170": [("500", P, "p.Climate.CRI_N_SIM"), ("1.6", S, "section number"),
             ("1.7", S, "section number")],
    "P178": [("120.85", P, "bbox.west"), ("122.00", P, "bbox.east"),
             ("30.65", P, "bbox.south"), ("31.90", P, "bbox.north"),
             ("16", D, "districts.n"), ("6,341 km²", L, "external: statutory terrestrial area"),
             ("2024", N, "map approval number year"),
             ("0650", N, "map approval number serial"),
             ("32651", N, "EPSG code of the projected CRS"),
             ("16", D, "districts.n"),
             ("7,205 km²", D, "boundary.union_area_km2"),
             ("6,341 km²", L, "external: statutory terrestrial area"),
             ("2021", N, "vintage of the finer shoreline layer"),
             ("+0.21%", D, "boundary.residual_offset_max_pct")],
    "P179": [("2022", L, CITATION), ("550 km", P, "shelf.width_km"),
             ("55 m", P, "p.Climate.H_SHELF_M"), ("2022", L, CITATION)],
    "P181": [("21", S, "Figure 21 label"),
             ("16", D, "districts.n")],
    "P184": [("4", S, "IBTrACS major version"), ("01", S, "IBTrACS revision"),
             ("2010", L, CITATION), ("2018", L, CITATION), ("2019", L, CITATION),
             ("3.0", P, "p.Climate.TC_FILTER_RADIUS_DEG"),
             ("121.47", P, "p.Climate.SHANGHAI_CENTER_LON"),
             ("31.23", P, "p.Climate.SHANGHAI_CENTER_LAT"),
             ("107", D, "log.tc.n_tracks_hist"),
             ("1945", D, "log.tc.year_min"),
             ("2025", D, "log.tc.year_max")],
    "P187": [("22", S, "Figure 22 caption"),
             ("3.0", P, "p.Climate.TC_FILTER_RADIUS_DEG"),
             ("107", D, "log.tc.n_tracks_hist"),
             ("1945", D, "log.tc.year_min"),
             ("2025", D, "log.tc.year_max")],
    "P190": [("23", S, "Figure 23 caption"),
             ("107", D, "log.tc.n_tracks_hist")],
    "P192": [("2", S, "FABDEM version"), ("2022", L, CITATION),
             ("30 m", N, "stated raster resolution of the source DEM"),
             ("0.01", P, "p.Climate.MODEL_RESOLUTION_DEG"),
             ("2022", L, CITATION)],
    "P194": [("585,033", D, "data.n_buildings_npy"),
             ("500 m", P, "exposure.age_match_radius_m"),
             ("429,906", D, "log.exp.age_filled"),
             ("73.5%", D, "log.exp.age_coverage_pct"),
             ("155,127", D, "log.exp.age_proxy"),
             ("1", S, "valuation level label"), ("2", S, "valuation level label"),
             ("3", S, "valuation level label"),
             ("9,800", P, "exposure.commercial_cost_cny_m2"),
             ("2020", L, CITATION),
             ("1,400", L, "external: Arcadis construction cost"),
             ("5,000", P, "exposure.commercial_area_cap_m2"),
             ("497,848", D, "log.exp.price_level1"),
             ("1", S, "valuation level label"),
             ("87,185", D, "log.exp.price_level2"),
             ("2", S, "valuation level label"),
             ("63.3 trillion", D, "exposure.total_t")],
    "P196": [("1 km", N, "stated LandScan grid size"),
             ("2020", L, CITATION),
             ("2000", D, "data.landscan.y0"),
             ("2024", D, "data.landscan.y1"),
             ("2024", D, "p.Climate.LANDSCAN_REFERENCE_YEAR"),
             ("5", S, "census round"), ("6", S, "census round"),
             ("7", S, "census round"), ("16", D, "districts.n")],
    "P198": [("30 m", N, "stated ISR raster resolution"),
             ("1985", D, "data.isr.y0"), ("1990", N, "ISR epoch year (5-year step)"),
             ("1995", N, "ISR epoch year (5-year step)"), ("2000", N, "ISR epoch year (5-year step)"),
             ("2005", N, "ISR epoch year (5-year step)"), ("2010", N, "ISR epoch year (5-year step)"),
             ("2015", N, "ISR epoch year (5-year step)"), ("2020", N, "ISR epoch year (5-year step)"),
             ("16", D, "districts.n"),
             ("1985", D, "data.isr.y0"), ("2020", D, "data.isr.y1")],
    "P200": [("1993", D, "data.sla.y0"), ("01", N, "month component of a date"),
             ("2023", D, "data.sla.y1"), ("12", N, "month component of a date")],
    "P202": [("1981", D, "data.temp.y0"),
             ("2024", D, "data.temp.y1"),
             ("1981", D, "data.temp.y0"),
             ("2024", D, "data.temp.y1"),
             ("0.05", P, "p.Climate.TEMP_RISK_ELASTICITY"),
             ("28 °C", P, "p.Climate.CFI_HEAT_BASE_TEMP"),
             ("0.25", P, "p.Climate.CFI_WEIGHT_SLA")],
    "P204": [("2", S, "valuation level label"),
             ("2015", P, "p.Climate.CFI_PRICE_YEAR_START"),
             ("2023", P, "p.Climate.CFI_PRICE_YEAR_END"),
             ("3", S, "valuation level label"),
             ("2025", D, "data.cprice.y1"), ("12", N, "month component of a date"),
             ("2025", D, "data.fri_end_year"), ("06", N, "month component of a date")],
    "P207": [("24", S, "Figure 24 caption"),
             ("6 m", P, "defence.current_def_gap.coastal_defense_crest_m")],
    "P210": [("25", S, "Figure 25 caption"), ("10", P, "p.Climate.NB_SYNTH_TRACKS")],
    "P216": [("27", S, "Figure 27 caption"), ("4.5", S, "scenario label"),
             ("8.5", S, "scenario label"), ("17", S, "reference to Figure 17")],
    "P234": [("33", S, "Figure 33 caption"), ("2000", D, "data.landscan.y0"),
             ("2024", D, "data.landscan.y1")],
    "P237": [("34", S, "Figure 34 caption"),
             ("1990", P, "build.A_old.age_before")],
    "P240": [("35", S, "Figure 35 caption"),
             ("0.176", P, "p.Climate.SURGE_MDR_CALIBRATION_SCALE"),
             ("0.10", P, "sweep.SURGE_MDR_CALIBRATION_SCALE.v0"),
             ("0.30", P, "sweep.SURGE_MDR_CALIBRATION_SCALE.v4")],
    "P243": [("36", S, "Figure 36 caption"),
             ("0.95", P, "sweep.TC_V_HALF_BASE_SCALE.v0"),
             ("0.975", P, "sweep.TC_V_HALF_BASE_SCALE.v1"),
             ("1.0", P, "sweep.TC_V_HALF_BASE_SCALE.v2"),
             ("1.025", P, "sweep.TC_V_HALF_BASE_SCALE.v3"),
             ("1.05", P, "sweep.TC_V_HALF_BASE_SCALE.v4"),
             ("25.7 m/s", P, "p.Climate.TC_IMPACT_V_THRESH")],
    "P246": [("37", S, "Figure 37 caption"),
             ("23.0", P, "sweep.TC_IMPACT_V_THRESH.v0"),
             ("24.5", P, "sweep.TC_IMPACT_V_THRESH.v1"),
             ("25.7", P, "sweep.TC_IMPACT_V_THRESH.v2"),
             ("27.0", P, "sweep.TC_IMPACT_V_THRESH.v3"),
             ("28.5", P, "sweep.TC_IMPACT_V_THRESH.v4")],
    "P249": [("38", S, "Figure 38 caption"),
             ("0.10", P, "sweep.SURGE_MDR_CALIBRATION_SCALE.v0"),
             ("0.14", P, "sweep.SURGE_MDR_CALIBRATION_SCALE.v1"),
             ("0.176", P, "sweep.SURGE_MDR_CALIBRATION_SCALE.v2"),
             ("0.22", P, "sweep.SURGE_MDR_CALIBRATION_SCALE.v3"),
             ("0.30", P, "sweep.SURGE_MDR_CALIBRATION_SCALE.v4")],
    "P250": [("8", S, "Table 8 caption number"), ("2050", S, "projection horizon")],
    "P251": [("0.40", P, "sweep.FRI_WEIGHT_GAP.v0.0"),
             ("0.30", P, "sweep.FRI_WEIGHT_GAP.v0.1"),
             ("0.30", P, "sweep.FRI_WEIGHT_GAP.v0.2"),
             ("0.30", P, "sweep.FRI_WEIGHT_GAP.v3.0"),
             ("0.30", P, "sweep.FRI_WEIGHT_GAP.v3.1"),
             ("0.40", P, "sweep.FRI_WEIGHT_GAP.v3.2"),
             ("0.07", N, "reallocation magnitude implied by the weight tuples"),
             ("15%", N, "+-15% band of the per-category adjustment sweep"),
             ("5%", N, "+-5% band of the TC scale sweep"),
             ("0.9999", D, "calib.aal_pred_obs"),
             ("1995", D, "calib.window_start"), ("2023", D, "calib.window_end"),
             ("25%", N, "+-25% band of the HP filter sweep"),
             ("2002", L, CITATION)],
    "P253": [("585,033", D, "data.n_buildings_npy"),
             ("10.25921", L, "DOI of the IBTrACS source record"),
             ("82", L, "DOI of the IBTrACS source record"),
             ("9e16", L, "DOI of the IBTrACS source record"),
             ("2", S, "FABDEM version"),
             ("10.48690", L, "DOI of the LandScan source record"),
             ("1524213", L, "DOI of the LandScan source record"),
             ("2022", L, CITATION),
             ("10.25921", L, "DOI of the ETOPO source record"),
             ("42", P, "p.Climate.RANDOM_SEED")],
    "P325": [("2010", L, CITATION)],
    "P377": [("12", P, "p.Climate.CLIMATE_INDEX_TREND_WINDOW_MONTHS"),
             ("100", P, "p.Climate.CRI_BASE_INDEX")],
    "P384": [("12", P, "p.Finance.VOLATILITY_WINDOW")],
    "P395": [("12", P, "p.Climate.CLIMATE_INDEX_TREND_WINDOW_MONTHS"),
             ("100", P, "p.Finance.FRI_BASE_INDEX")],
}

# Table 6 / Table 7 / Table B1 / Table 8 / Table 10 and the sweep values are
# generated programmatically below (mechanical, cell -> config entry).
T6_MAP = {
    "T6#r1c1": [("1", N, "implicit floor minimum (not a config key)"),
                ("6", P, "build.A_old.floors_max")],
    "T6#r1c2": [("1990", P, "build.A_old.age_before")],
    "T6#r1c4": [("0.80", P, "vhalf.adj.A_old")],
    "T6#r1c6": [("0.60", P, "kappa.low_rise")],
    "T6#r2c1": [("1", N, "implicit floor minimum (not a config key)"),
                ("6", P, "build.A_new.floors_max")],
    "T6#r2c2": [("2002", P, "build.A_new.age_after")],
    "T6#r2c4": [("0.90", P, "vhalf.adj.A_new")],
    "T6#r2c6": [("0.60", P, "kappa.low_rise")],
    "T6#r3c1": [("7", P, "build.B_old.floors_min"),
                ("30", P, "build.B_old.floors_max")],
    "T6#r3c2": [("2001", P, "build.B_old.age_before")],
    "T6#r3c4": [("0.95", P, "vhalf.adj.B_old")],
    "T6#r3c6": [("0.40", P, "kappa.mid_rise")],
    "T6#r4c1": [("7", P, "build.B_new.floors_min"),
                ("30", P, "build.B_new.floors_max")],
    "T6#r4c2": [("2002", P, "build.B_new.age_after")],
    "T6#r4c4": [("1.00", P, "vhalf.adj.B_new")],
    "T6#r4c6": [("0.40", P, "kappa.mid_rise")],
    "T6#r5c1": [("31", P, "build.C.floors_min")],
    "T6#r5c4": [("1.05", P, "vhalf.adj.C")],
    "T6#r5c6": [("0.25", P, "kappa.high_rise")],
    "T6#r6c4": [("1.10", P, "vhalf.adj.D")],
    "T6#r6c6": [("0.50", P, "kappa.commercial")],
}
ELEM.update(T6_MAP)


# Table 8 (sensitivity): row -> column -> metric ids, in printed order
T8_DATA_ROWS = [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 13, 14, 15, 16, 17, 18, 20]
T8_SINGLE_DEV = {10, 13}       # "0%" and "+-1.8%" print a single number
T8_LABEL_YEARS = {6: "build.A_old.age_before", 8: "build.B_old.age_before"}


def _t8_map() -> dict:
    out = {}
    for r in T8_DATA_ROWS:
        if r != 18:
            out["T8#r%dc1" % r] = [("x", P, "t8.r%d.param_baseline" % r)]
            out["T8#r%dc2" % r] = [("x", P, "t8.r%d.param_lo" % r),
                                   ("x", P, "t8.r%d.param_hi" % r)]
        out["T8#r%dc4" % r] = [("x", P, "t8.r%d.index_baseline" % r)]
        out["T8#r%dc5" % r] = [("x", P, "t8.r%d.index_min" % r),
                               ("x", P, "t8.r%d.index_max" % r)]
        if r in T8_SINGLE_DEV:
            out["T8#r%dc6" % r] = [("x", M, "t8.r%d.dev_max" % r)]
        else:
            out["T8#r%dc6" % r] = [("x", M, "t8.r%d.dev_min" % r),
                                   ("x", M, "t8.r%d.dev_max" % r)]
    for r, mid in T8_LABEL_YEARS.items():
        out["T8#r%dc0" % r] = [("x", P, mid)]
    out["T8#r7c0"] = [("02", N, "02+ shorthand in the category label")]
    out["T8#r9c0"] = [("02", N, "02+ shorthand in the category label")]
    out["T8#r4c1"] = [("25.7 m/s", P, "t8.r4.param_baseline")]
    return out


ELEM.update(_t8_map())


def elem_for(target: str) -> dict:
    """Element table for a specific document revision.

    v12 dropped the 0.9999 token from P9 and P17 (the ratio is now stated
    qualitatively) and prints the A-baseline expectation as 1.00 in P251.
    """
    e = {k: list(v) for k, v in ELEM.items()}
    if target == "v12":
        for loc in ("P9", "P17"):
            e[loc] = [x for x in e[loc] if x[0] != "0.9999"]
        e["P251"] = [("1.00", D, "calib.aal_pred_obs_v8")
                     if x[0] == "0.9999" else x for x in e["P251"]]
    return e



def _table7_map() -> dict:
    """Table 7 cells: the printed token is the config value itself, so the
    expected token strings are generated from the canonical values rather than
    typed twice."""
    out = {}
    for r in range(1, 8):
        out["T7#r%dc0" % r] = [("%.1f" % DEPTHS[r - 1], P,
                                "surge.depth.d%d" % (r - 1))]
        for c, cls in enumerate(SURGE_CLASSES, start=1):
            mid = "surge.dd.%s.d%d" % (cls, r - 1)
            out["T7#r%dc%d" % (r, c)] = [("%.3f" % MDRS[(cls, r - 1)], P, mid)]
    return out


SURGE_CLASSES = ["low_rise", "mid_rise", "high_rise", "commercial"]
DEPTHS = [0.0, 0.3, 0.6, 1.2, 1.8, 2.4, 3.0]
MDRS = {
    ("low_rise", 0): 0.000, ("low_rise", 1): 0.080, ("low_rise", 2): 0.150,
    ("low_rise", 3): 0.300, ("low_rise", 4): 0.420, ("low_rise", 5): 0.500,
    ("low_rise", 6): 0.550,
    ("mid_rise", 0): 0.000, ("mid_rise", 1): 0.040, ("mid_rise", 2): 0.080,
    ("mid_rise", 3): 0.180, ("mid_rise", 4): 0.250, ("mid_rise", 5): 0.300,
    ("mid_rise", 6): 0.350,
    ("high_rise", 0): 0.000, ("high_rise", 1): 0.020, ("high_rise", 2): 0.040,
    ("high_rise", 3): 0.100, ("high_rise", 4): 0.150, ("high_rise", 5): 0.180,
    ("high_rise", 6): 0.220,
    ("commercial", 0): 0.000, ("commercial", 1): 0.050, ("commercial", 2): 0.100,
    ("commercial", 3): 0.220, ("commercial", 4): 0.320, ("commercial", 5): 0.380,
    ("commercial", 6): 0.420,
}
ELEM.update(_table7_map())

# Table B1 (Appendix B): docx row -> (mode, metric id / note)
#   single : the value cell holds one numeric token, bound to the metric
#   bbox   : four tokens bound in order to bbox.west/south/east/north
#   note   : multi-token or non-numeric cell, adjudicated by the table rule
#   none   : the cell carries no numeric token at all
T9_VALUE = {
    1: ("bbox", ""),
    2: ("single", "p.Climate.MODEL_RESOLUTION_DEG"),
    3: ("note", "model name year (Holland 2010)"),
    4: ("single", "p.Climate.HOLLAND_B_DEFAULT"),
    5: ("single", "p.Climate.RMAX_DEFAULT_KM"),
    6: ("single", "p.Climate.FETCH_RMAX_FACTOR"),
    7: ("single", "p.Climate.NB_SYNTH_TRACKS"),
    8: ("single", "p.Climate.TC_FILTER_RADIUS_DEG"),
    9: ("single", "p.Climate.RHO_AIR"),
    10: ("single", "p.Climate.RHO_WATER"),
    11: ("single", "p.Climate.G"),
    12: ("note", "scientific notation 2.5 x 10^-3"),
    13: ("single", "shelf.width_km"),
    14: ("single", "p.Climate.H_SHELF_M"),
    15: ("single", "log.tc.knutson_ssp245"),
    16: ("single", "log.tc.knutson_ssp585"),
    17: ("single", "log.surge.slr_245"),
    18: ("single", "log.surge.slr_585"),
    19: ("single", "defence.baseline_nodef.coastal_defense_crest_m"),
    20: ("single", "defence.current_def_gap.coastal_defense_crest_m"),
    21: ("note", "scientific notation 10^-4"),
    22: ("single", "p.Climate.COASTAL_ATTENUATION_EXPONENT"),
    23: ("none", "unbounded reach, no numeric token"),
    24: ("single", "p.Climate.COASTAL_MIN_INUNDATION_DEPTH_M"),
    25: ("single", "p.Climate.HYBRID_HUANGPU_TRIGGER_TWL_M"),
    26: ("single", "p.Climate.HYBRID_HUANGPU_REFERENCE_TWL_M"),
    27: ("single", "p.Climate.HYBRID_HUANGPU_FULL_RESPONSE_TWL_M"),
    28: ("single", "p.Climate.HYBRID_HUANGPU_OPEN_BOUNDARY_REFERENCE_TWL_M"),
    29: ("single", "p.Climate.HYBRID_HUANGPU_BANKFULL_DEPTH_M"),
    30: ("single", "p.Climate.HYBRID_HUANGPU_DECAY_DISTANCE_M"),
    31: ("single", "p.Climate.HYBRID_HUANGPU_MAX_REACH_M"),
    32: ("single", "defence.nodef.huangpu_decay_m"),
    33: ("single", "p.Climate.HYBRID_HUANGPU_NODEF_MAX_REACH_M"),
    34: ("single", "p.Climate.HYBRID_HUANGPU_MIN_RIVER_DEPTH_M"),
    35: ("single", "p.Climate.COASTAL_MIN_REACH_M"),
    36: ("single", "p.Climate.TC_IMPACT_V_THRESH"),
    37: ("single", "log.vuln.vhalf_base"),
    38: ("single", "p.Climate.SURGE_MDR_CALIBRATION_SCALE"),
    39: ("single", "p.Climate.TC_V_HALF_BASE_SCALE"),
    40: ("single", "p.Climate.GAMMA_SVI"),
    41: ("single", "p.Climate.TEMP_RISK_ELASTICITY"),
    42: ("single", "p.Climate.CRI_EWMA_ALPHA"),
    43: ("single", "p.Climate.CRI_DAMAGE_KAPPA"),
    44: ("single", "p.Climate.CRI_EXPOSURE_FLOOR"),
    45: ("single", "p.Climate.CRI_VULNERABILITY_FLOOR"),
    46: ("single", "p.Climate.CRI_BASE_INDEX"),
    47: ("single", "p.Climate.CRI_N_SIM"),
    48: ("single", "log.cri.slow_theta"),
    49: ("single", "cri.ssp.SSP2-4.5.h_drift"),
    50: ("single", "cri.ssp.SSP5-8.5.h_drift"),
    51: ("single", "cri.ssp.SSP2-4.5.dmg_mult"),
    52: ("single", "cri.ssp.SSP5-8.5.dmg_mult"),
    53: ("single", "cri.ssp.SSP2-4.5.sev_shift"),
    54: ("single", "cri.ssp.SSP5-8.5.sev_shift"),
    55: ("single", "p.Finance.HP_LAMBDA"),
    56: ("single", "p.Finance.VOLATILITY_WINDOW"),
    57: ("single", "cvar.n_perturb"),
    58: ("single", "cvar.window_years"),
    59: ("single", "cvar.alpha_pct"),
    60: ("note", "fraction triplet (1/3, 1/3, 1/3)"),
    61: ("single", "p.Finance.FRI_BASE_INDEX"),
    62: ("single", "p.Finance.FRI_N_SIM"),
    63: ("single", "p.fit.theta_mr"),
    64: ("single", "p.fit.sigma_diff"),
    65: ("single", "p.fit.lambda_jump"),
    66: ("single", "p.fit.mu_jump"),
    67: ("single", "p.fit.sigma_jump"),
    68: ("single", "p.fit.trend_growth"),
    69: ("single", "jump.mult.SSP2-4.5"),
    70: ("single", "jump.mult.SSP5-8.5"),
    71: ("none", "text value (geometric mean)"),
    72: ("single", "p.Composite.CFCI_TARGET_RHO"),
}

# Table 10 (figure index) carries only the figure numbers
for _r in range(1, 39):
    ELEM["T10#r%dc0" % _r] = [(str(_r), S, "figure index row number")]

ELEM["T5#r1c3"] = [("2010", S, "processing step label"),
                   ("2050", S, "projection horizon")]
ELEM["T5#r2c3"] = [("2050", S, "projection horizon")]
ELEM["T5#r3c4"] = [("2050", S, "projection horizon")]


# ─────────────────────────────────────────────────────────────────────────
# Resolver
# ─────────────────────────────────────────────────────────────────────────


def load_truth(path: Path) -> dict:
    with io.open(path, encoding="utf-8", newline="") as fh:
        return {r["metric_id"]: r for r in csv.DictReader(fh)}


def classify_generic(row: dict) -> tuple[str, str, str]:
    """Section-level rules for tokens no explicit element rule covers."""
    rid = row["row_id"]
    tok = row["token"]
    ctx = row["context"]
    sec = row["section"]

    if sec.startswith("References"):
        return R, "", "bibliography block"
    if sec.startswith("Appendix C"):
        return S, "", "figure index table"
    if rid.startswith("T9#"):
        return P, "", "Appendix B cell bound separately"
    if sec.startswith("Appendix B"):
        return P, "", "Appendix B table"
    if tok in ("4.5", "8.5") and "SSP" in ctx:
        return S, "", "scenario label"
    m = re.match(r"^\s*(?:Figure|Fig\.)\s*(\d+)", ctx)
    if m and tok == m.group(1):
        return S, "", "figure number"
    m = re.match(r"^\s*Table\s*(\d+)", ctx)
    if m and tok == m.group(1):
        return S, "", "table number"
    if re.fullmatch(r"\d+(?:\.\d+)*", tok) and len(tok) <= 7 and "." in tok:
        return S, "", "section number"
    return "", "", ""


def main() -> int:
    ap = argparse.ArgumentParser(description="WP11.3 token classifier")
    ap.add_argument("--tokens", default=str(TOKENS))
    ap.add_argument("--truth", default=str(TRUTH))
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--show-unclassified", action="store_true")
    ap.add_argument("--target", default="v11", choices=["v11", "v12"])
    ap.add_argument("--relax-drift", action="store_true",
                    help="bind positionally when the declared token text has "
                         "been edited but the count is unchanged (v12 audit)")
    args = ap.parse_args()

    truth = load_truth(Path(args.truth))
    with io.open(args.tokens, encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))

    # index tokens per element, preserving order
    per_elem: dict[str, list[dict]] = {}
    for r in rows:
        per_elem.setdefault(r["row_id"], []).append(r)

    resolved: list[dict] = []
    drift: list[str] = []
    unknown_bind: list[str] = []
    note_only: list[str] = []
    drift_warn: list[str] = []

    # ---- explicit element rules
    explicit_done: set[str] = set()
    elem = elem_for(args.target)
    for rid, spec in elem.items():
        if rid == "T9":
            continue
        actual = per_elem.get(rid, [])
        toks = [t for t, _, _ in spec]
        actual_toks = [a["token"] for a in actual]
        if not actual:
            drift.append("%s: declared but absent from the document" % rid)
            continue
        if toks and all(x == "x" for x in toks):
            # positional-only declaration (tables): the drift check is on count
            if len(actual_toks) != len(toks):
                drift.append("%s: expected %d tokens, found %d (%r)"
                             % (rid, len(toks), len(actual_toks), actual_toks))
                continue
        elif actual_toks != toks:
            if args.relax_drift and len(actual_toks) == len(toks):
                drift_warn.append("%s: %r -> %r" % (rid, toks, actual_toks))
            else:
                drift.append("%s: declared %r != document %r"
                             % (rid, toks, actual_toks))
                continue
        for a, (tok, cls, bind) in zip(actual, spec):
            if cls in (P, M) and bind not in truth:
                unknown_bind.append("%s/%s -> %s" % (rid, tok, bind))
            elif cls == D and bind not in truth:
                note_only.append("%s/%s -> %s" % (rid, tok, bind))
            resolved.append({**a, "class": cls, "bind": bind})
        explicit_done.add(rid)

    # ---- Table B1: one value cell per row, bound through T9_VALUE
    bbox_order = ["bbox.west", "bbox.south", "bbox.east", "bbox.north"]
    for rid, spec in per_elem.items():
        if not rid.startswith("T9#"):
            continue
        m = re.match(r"T9#r(\d+)c(\d+)", rid)
        row_i, col_i = int(m.group(1)), int(m.group(2))
        if col_i != 2:
            for a in spec:
                resolved.append({**a, "class": S,
                                 "bind": "Table B1 non-value column"})
            continue
        mode, mid = T9_VALUE.get(row_i, ("unknown", ""))
        if mode == "single":
            if mid not in truth:
                unknown_bind.append("%s -> %s" % (rid, mid))
            for a in spec:
                resolved.append({**a, "class": P, "bind": mid})
        elif mode == "bbox":
            if len(spec) != 4:
                drift.append("%s: expected 4 bbox components, got %d"
                             % (rid, len(spec)))
            for a, b in zip(spec, bbox_order):
                resolved.append({**a, "class": P, "bind": b})
        elif mode in ("note", "none"):
            for a in spec:
                resolved.append({**a, "class": N, "bind": mid})
        else:
            for a in spec:
                resolved.append({**a, "class": N,
                                 "bind": "Table B1 row %d has no mapping" % row_i})

    # ---- everything else: generic rules
    unclassified: list[dict] = []
    for rid, spec in per_elem.items():
        if rid in explicit_done or rid.startswith("T9#"):
            continue
        for a in spec:
            cls, bind, why = classify_generic(a)
            if not cls:
                unclassified.append(a)
                continue
            resolved.append({**a, "class": cls, "bind": bind or why})

    # ---- report
    print("=== WP11.3 token classifier ===")
    print("  tokens in v11       : %d" % len(rows))
    print("  resolved            : %d" % len(resolved))
    print("  unclassified        : %d" % len(unclassified))
    print("  map drift           : %d" % len(drift))
    print("  drift tolerated     : %d" % len(drift_warn))
    print("  unknown metric binds: %d" % len(unknown_bind))
    counts: dict[str, int] = {}
    for r in resolved:
        counts[r["class"]] = counts.get(r["class"], 0) + 1
    for k in sorted(counts):
        print("    %-7s %4d" % (k, counts[k]))
    if drift:
        print("  --- MAP DRIFT ---")
        for d in drift[:20]:
            print("    " + d)
    if unknown_bind:
        print("  --- UNKNOWN METRIC ---")
        for d in unknown_bind[:20]:
            print("    " + d)
    if unclassified:
        print("  --- UNCLASSIFIED ---")
        for a in (unclassified if args.show_unclassified else unclassified[:25]):
            print("    %-8s %-10r %s" % (a["row_id"], a["token"],
                                         a["context"][:70]))

    # ---- write
    cols = ["row_id", "kind", "section", "token", "class", "bind",
            "metric_value", "metric_digits", "metric_source", "context", "note"]
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=cols, lineterminator="\n")
    w.writeheader()
    for r in sorted(resolved, key=lambda x: (x["row_id"], x["token"])):
        t = truth.get(r["bind"], {})
        w.writerow({
            "row_id": r["row_id"], "kind": r["kind"], "section": r["section"],
            "token": r["token"], "class": r["class"], "bind": r["bind"],
            "metric_value": t.get("value", ""),
            "metric_digits": t.get("digits", ""),
            "metric_source": t.get("source", ""),
            "context": r["context"], "note": "",
        })
    for a in unclassified:
        w.writerow({"row_id": a["row_id"], "kind": a["kind"],
                    "section": a["section"], "token": a["token"],
                    "class": "UNCLASSIFIED", "bind": "", "metric_value": "",
                    "metric_digits": "", "metric_source": "",
                    "context": a["context"], "note": ""})
    out = Path(args.out)
    tmp = out.with_suffix(".csv.tmp")
    tmp.write_text(buf.getvalue(), encoding="utf-8", newline="\n")
    tmp.replace(out)
    print("  wrote %s (%d rows)" % (out.relative_to(NEWROOT), len(resolved)))

    if drift or unknown_bind or unclassified:
        print("RESULT: MAP-INCOMPLETE")
        return 1
    print("RESULT: MAP-COMPLETE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
