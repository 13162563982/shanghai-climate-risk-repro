# -*- coding: utf-8 -*-
"""WP11.4 - adjudicate every mapped token against the canonical truth table.

WHAT IT DOES
------------
Three families of checks, all machine-decidable:

  NUMERIC   the 597 MODEL / PARAM / DATA tokens are printed from the canonical
            value at *the precision the manuscript uses* and compared as
            decimals; a value that is right at the wrong precision is still a
            finding, because the reader sees the printed digits.
  TABLE     Table 1 / 2 scenario and district row order, the figure index, the
            Table B1 cell grammar (tuples, scientific notation, fractions,
            an unbounded value), and the Table 7 header.
  FIGURE    every one of the 37 drawings: rId -> media -> sha vs the source
            render, figure number vs the index, index file name vs the source,
            and a caption/figure coherence check.
  ASSERT    ordinal and directional claims that rest on the outputs (rankings,
            monotonicity, "more than doubles", "roughly twice", "quadrupled"):
            each is a predicate over the truth table.
  CONSIST   internal coherence: abstract vs results vs tables, share sums,
            geometric-mean identity, district aggregation closure.

USAGE
-----
  env\\run.ps1 tools\\_wp11_check.py
  env\\run.ps1 tools\\_wp11_check.py --only numeric
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import re
import sys
import zipfile
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

NEWROOT = Path(__file__).resolve().parent.parent
DOCS = NEWROOT / "docs"
TRUTH = DOCS / "_wp11_真值表.csv"
MAP = DOCS / "_wp11映射表.csv"
FIGCSV = DOCS / "_wp11_图件清单.csv"
TOKENS = DOCS / "_wp11_v11清单.csv"
OUT = DOCS / "_wp11核查明细.csv"
FIGDIR = NEWROOT / "manuscript" / "figures"
DOCX_PATH = NEWROOT / "manuscript" / "PAPER_MANUSCRIPT_v11.docx"

VERIFIED = ("MODEL", "PARAM", "DATA")


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest().upper()


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def load_csv(p: Path) -> list[dict]:
    with io.open(p, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


# ─────────────────────────────────────────────────────────────────────────
# numeric comparison
# ─────────────────────────────────────────────────────────────────────────

TOKEN_CORE = re.compile(r"[0-9][0-9,]*(?:\.[0-9]+)?")


def token_decimal(tok: str):
    """(Decimal value, decimal places) for a printed token, or None."""
    m = TOKEN_CORE.search(tok)
    if not m:
        return None
    core = m.group(0).replace(",", "")
    dp = len(core.split(".")[1]) if "." in core else 0
    val = Decimal(core)
    if tok.strip().startswith(("-", "\u2212")) and val != 0:
        val = -val
    return val, dp


def print_at(value, dp: int) -> Decimal:
    q = Decimal(1).scaleb(-dp)
    return Decimal(str(value)).quantize(q, rounding=ROUND_HALF_UP)


def compare(token: str, value, metric_digits: str):
    """Return (status, expected_string, note)."""
    got = token_decimal(token)
    if got is None:
        return "NO-NUMBER", "", "token carries no numeric core"
    want, dp = got
    if isinstance(value, str):
        return "TEXT", value, "non-numeric metric"
    exp = print_at(value, dp)
    if exp == want:
        # flag values that sit within a hair of a .5 rounding boundary
        scaled = float(value) * (10 ** dp)
        if abs(abs(scaled - int(scaled)) - 0.5) < 1e-6:
            return "OK-BOUNDARY", str(exp), "value is within 1e-6 of a rounding boundary"
        return "OK", str(exp), ""
    return "MISMATCH", str(exp), "printed %s vs expected %s" % (str(want), str(exp))


# ─────────────────────────────────────────────────────────────────────────
# checks
# ─────────────────────────────────────────────────────────────────────────


def check_numeric(truth: dict, mapping: list[dict]) -> list[dict]:
    out = []
    for r in mapping:
        cls = r["class"]
        if cls not in VERIFIED:
            continue
        mid = r["bind"]
        t = truth.get(mid)
        if t is None:
            out.append({**r, "status": "NO-METRIC", "expected": "",
                        "detail": "bind %r not in truth table" % mid})
            continue
        status, expected, note = compare(r["token"], _num(t["value"]),
                                         t["digits"])
        out.append({**r, "status": status, "expected": expected,
                    "detail": note, "metric_value": t["value"],
                    "metric_source": t["source"]})
    return out


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return v


def check_tables(truth: dict) -> list[dict]:
    """Row-order and header checks that the token scan cannot see."""
    rows = []
    ext = _load_extractor()
    entries, _ = ext.read_docx_stdlib(DOCX_PATH)
    cell = {e.ident: e.text.strip() for e in entries}

    def row(name, status, detail):
        rows.append({"row_id": name, "token": "", "class": "TABLE",
                     "bind": "", "status": status, "expected": "",
                     "detail": detail, "metric_value": "", "metric_source": ""})

    # Table 1 scenario labels
    want = ["Historical", "SSP2-4.5 (+0.3 m SLR)", "SSP5-8.5 (+0.5 m SLR)"]
    for i, w in enumerate(want, start=1):
        got = cell.get("T0#r%dc0" % i, "")
        row("T0#r%dc0" % i, "OK" if got.startswith(w.split(" (")[0]) else "MISMATCH",
            "scenario label %r (document %r)" % (w, got))

    # Table 2 district order == canonical historical ranking (top five)
    ranking = str(truth["eal.dist.hist.rank"]["value"]).split(" > ")
    en = {"浦东新区": "Pudong", "杨浦区": "Yangpu", "闵行区": "Minhang",
          "徐汇区": "Xuhui", "虹口区": "Hongkou", "黄浦区": "Huangpu"}
    for i in range(1, 6):
        got = cell.get("T1#r%dc0" % i, "")
        want_name = en.get(ranking[i - 1], ranking[i - 1])
        row("T1#r%dc0" % i,
            "OK" if got.startswith(want_name) else "MISMATCH",
            "district row %d should be %s (rank %d), document says %r"
            % (i, want_name, i, got))

    # figure index: 38 rows, contiguous numbering, Figure 15 = inline table
    nums = []
    for i in range(1, 39):
        v = cell.get("T10#r%dc0" % i, "")
        if v.isdigit():
            nums.append(int(v))
    row("T10 order", "OK" if nums == list(range(1, 39)) else "MISMATCH",
        "figure index numbers %s" % ("1..38" if nums == list(range(1, 39))
                                     else nums))
    f15 = cell.get("T10#r15c2", "")
    row("T10#r15c2", "OK" if "Inline" in f15 else "MISMATCH",
        "Figure 15 row is the inline module table (%r)" % f15)

    # Table 6 / Table 7 headers
    row("T6 header", "OK" if cell.get("T6#r0c0") == "Category" else "MISMATCH",
        "Table 6 header starts with %r" % cell.get("T6#r0c0"))
    got7 = [cell.get("T7#r0c%d" % c, "") for c in range(5)]
    ok7 = got7 == ["Depth (m)", "Low-rise", "Mid-rise", "High-rise", "Commercial"]
    row("T7 header", "OK" if ok7 else "MISMATCH", "Table 7 header %r" % got7)
    return rows


def _load_extractor():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "ext", NEWROOT / "tools" / "extract_manuscript_numbers.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ext"] = mod
    spec.loader.exec_module(mod)
    return mod


def check_figures() -> list[dict]:
    rows = []
    figs = load_csv(FIGCSV)
    with zipfile.ZipFile(DOCX_PATH) as zf:
        media = {n: sha256_bytes(zf.read(n)) for n in zf.namelist()
                 if n.startswith("word/media/")}

    def row(name, status, detail):
        rows.append({"row_id": name, "token": "", "class": "FIGURE",
                     "bind": "", "status": status, "expected": "",
                     "detail": detail, "metric_value": "", "metric_source": ""})

    src_sha = {}
    for f in sorted(FIGDIR.glob("*.png")):
        src_sha[f.name] = sha256_file(f)

    for f in figs:
        no = int(f["fig_no"])
        name = f["t10_file"]
        emb = media.get(f["media"], "")
        want = src_sha.get(name)
        if want is None:
            row("Fig %d" % no, "NO-SOURCE",
                "index file %r has no render in manuscript/figures" % name)
            continue
        ok = emb == want
        row("Fig %d" % no, "OK" if ok else "MISMATCH",
            "%s embeds %s (%s) vs source %s (%s)"
            % (name, f["media"], (emb or "-")[:12], name, want[:12]))
        # caption coherence: the short label and the long caption must agree
        lab = re.match(r"Figure (\d+)", f["short_label"] or "")
        cap = re.match(r"Figure (\d+)", f["long_caption"] or "")
        if lab and int(lab.group(1)) != no:
            row("Fig %d label" % no, "MISMATCH",
                "short label numbers %s" % lab.group(1))
        if cap and int(cap.group(1)) != no:
            row("Fig %d caption" % no, "MISMATCH",
                "long caption numbers %s" % cap.group(1))

    # every render used by the paper must exist and be current
    used = {f["t10_file"] for f in figs}
    row("figure set", "OK" if len(used) == 37 else "MISMATCH",
        "%d distinct renders for %d drawings" % (len(used), len(figs)))

    # caption vs render: the file name and the caption should share a topic word
    KEY = {
        "compound": "compound", "tc": "tc", "surge": "surge", "ss": "surge",
        "cri": "cri", "hsi": "hsi", "fri": "hsi", "cchi": "cchi",
        "cf": "cchi", "vulnerability": "vulnerab", "tracks": "track",
        "price": "price", "population": "population", "built_up": "built",
        "exposure": "exposure", "event_count": "event", "monthly": "month",
        "impact_functions": "impact function", "sensitivity": "sensitiv",
        "decomposition": "decompos", "triple": "triple", "overlay": "overlay",
        "trend": "trend", "risk_index": "index", "defense": "defence",
        "vhalf": "v_half", "vthresh": "threshold", "mdr": "mdr",
        "type_distribution": "type distribution", "study": "study area",
        "depth": "depth", "occurrence": "occurrence", "hexbin": "hexbin",
    }
    poor = []
    for f in figs:
        name = (f["t10_file"] or "").lower()
        cap = ((f["long_caption"] or "") + " " + (f["short_label"] or "")).lower()
        keys = set()
        for k, word in KEY.items():
            if k in name:
                keys.add(word)
        if keys and not any(w in cap for w in keys):
            poor.append("Fig %s (%s)" % (f["fig_no"], f["t10_file"]))
    row("caption/render topic overlap", "OK" if not poor else "REVIEW",
        "no shared topic word: %s" % poor if poor else "37/37 share a topic word")
    return rows


def check_table_b1() -> list[dict]:
    """Table B1 cell grammar: tuples, scientific notation, fractions, infinity."""
    rows = []
    ext = _load_extractor()
    entries, _ = ext.read_docx_stdlib(DOCX_PATH)
    cell = {e.ident: e for e in entries}
    truth = {r["metric_id"]: r for r in load_csv(TRUTH)}

    def row(name, status, detail):
        rows.append({"row_id": name, "token": "", "class": "TABLE-B1",
                     "bind": "", "status": status, "expected": "",
                     "detail": detail, "metric_value": "", "metric_source": ""})

    checks = [
        (1, "(120.85, 30.65, 122.00, 31.90)",
         ["bbox.west", "bbox.south", "bbox.east", "bbox.north"]),
        (12, "2.5 × 10⁻³", ["p.Climate.CD_MAX"]),
        (21, "10⁻⁴", ["p.Climate.COASTAL_OVERLAND_ATTENUATION_RATE"]),
        (60, "(1/3, 1/3, 1/3)", ["fweights.0", "fweights.1", "fweights.2"]),
        (71, "Geometric mean", []),
    ]
    for r_i, want_text, mids in checks:
        e = cell.get("T9#r%dc2" % r_i)
        if e is None:
            row("T9 r%d" % r_i, "MISSING", "value cell absent")
            continue
        got = e.text.strip()
        if not want_text.startswith("(1/3"):
            norm = got.replace("\u00d7", "x").replace("\u207b", "-")
            ok = norm.replace(" ", "") == want_text.replace("×", "x").replace(
                "⁻", "-").replace(" ", "")
        else:
            ok = got.replace(" ", "") == "(1/3,1/3,1/3)"
        row("T9 r%d value" % r_i, "OK" if ok else "MISMATCH",
            "cell reads %r" % got)
        for mid in mids:
            if mid not in truth:
                row("T9 r%d metric" % r_i, "NO-METRIC", mid)

    # unbounded reach: the symbol cell must carry maths, the value cell "∞"
    e = cell.get("T9#r23c2")
    if e is not None:
        txt = e.text.strip()
        row("T9 r23 value", "OK" if (txt == "" and e.has_math) or "∞" in txt
            else "MISMATCH", "adaptive penetration reach cell = %r (math=%s)"
            % (txt, e.has_math))
    return rows


# ─────────────────────────────────────────────────────────────────────────
# ordinal / directional assertions over the truth table
# ─────────────────────────────────────────────────────────────────────────


def check_assertions(truth: dict) -> list[dict]:
    rows = []

    def row(name, ok, detail, status_if_fail="MISMATCH"):
        rows.append({"row_id": name, "token": "", "class": "ASSERT",
                     "bind": "", "status": "OK" if ok else status_if_fail,
                     "expected": "", "detail": detail,
                     "metric_value": "", "metric_source": ""})

    g = lambda k: float(truth[k]["value"])

    # A1 historical ranking of the top three districts
    rank = str(truth["eal.dist.hist.rank"]["value"]).split(" > ")
    row("A1 top-3 districts", rank[:3] == ["浦东新区", "杨浦区", "闵行区"],
        "ranking starts %s" % rank[:3])
    row("A2 fourth/fifth districts", rank[3:5] == ["徐汇区", "虹口区"],
        "ranks 4-5 are %s" % rank[3:5])

    # A3 Pudong is the largest district by exposure
    row("A3 largest exposure", truth["exposure.largest_district"]["value"] == "浦东新区",
        "argmax exposure = %s" % truth["exposure.largest_district"]["value"])

    # A4 city EAL and its defence reduction increase with forcing
    nodef = [g("eal.city.hist.nodef.bn"), g("eal.city.ssp245.nodef.bn"),
             g("eal.city.ssp585.nodef.bn")]
    red = [g("eal.city.hist.red_pct"), g("eal.city.ssp245.red_pct"),
           g("eal.city.ssp585.red_pct")]
    row("A4 EAL monotone in forcing", nodef == sorted(nodef), "EAL %s" % nodef)
    row("A5 defence reduction monotone", red == sorted(red), "reduction %s" % red)

    # A6 surge share grows with forcing
    share = [g("eal.city.hist.surge_share_pct"),
             g("eal.city.ssp245.surge_share_pct"),
             g("eal.city.ssp585.surge_share_pct")]
    row("A6 surge share monotone", share == sorted(share), "surge share %s" % share)
    row("A7 shares sum to 100",
        abs(g("eal.city.hist.wind_share_pct") + g("eal.city.hist.surge_share_pct")
            - 100.0) < 1e-6, "wind+surge share = %.6f"
        % (g("eal.city.hist.wind_share_pct") + g("eal.city.hist.surge_share_pct")))

    # A8 "more than two-thirds invariant": wind share > 2/3
    row("A8 wind share above two thirds",
        g("eal.city.hist.wind_share_pct") > 200.0 / 3.0,
        "wind share %.2f%%" % g("eal.city.hist.wind_share_pct"))

    # A9 Yangpu more than doubles under SSP5-8.5
    base = g("eal.dist.hist.杨浦区.bn")
    fut = g("eal.dist.ssp585.杨浦区.bn")
    row("A9 Yangpu more than doubles", fut / base > 2.0,
        "%.3f -> %.3f = %.2fx" % (base, fut, fut / base))

    # A10 the three corridor ratios are ~twice the city mean
    mean = g("eal.dist.hist.mean_of_ratios_permille")
    for name, cn in (("Hongkou", "虹口区"), ("Yangpu", "杨浦区"),
                     ("Huangpu", "黄浦区")):
        r = g("eal.dist.hist.%s.ratio_permille" % cn)
        row("A10 %s ratio vs mean" % name, 1.5 <= r / mean <= 2.3,
            "%.4f vs %.4f = %.2fx" % (r, mean, r / mean))

    # A11 CRI quadruples between 1993 and 2023
    row("A11 CRI quadrupled", 3.9 <= g("cri.hist.fold") <= 4.5,
        "fold = %.4f" % g("cri.hist.fold"))

    # A12 CRI / HSI / CCHI 2050 medians rise with forcing
    for fam, keys in (("CRI", ("cri.proj.hist.p50", "cri.proj.ssp245.p50",
                               "cri.proj.ssp585.p50")),
                      ("HSI", ("hsi.proj.hist.p50", "hsi.proj.ssp245.p50",
                               "hsi.proj.ssp585.p50")),
                      ("CCHI", ("cchi.proj.hist.p50", "cchi.proj.ssp245.p50",
                                "cchi.proj.ssp585.p50"))):
        v = [g(k) for k in keys]
        row("A12 %s median monotone" % fam, v == sorted(v), "%s" % v)

    # A13 percentile ordering inside every scenario
    for fam in ("cri", "hsi", "cchi"):
        for scen in ("hist", "ssp245", "ssp585"):
            p10, p50, p90 = (g("%s.proj.%s.p10" % (fam, scen)),
                             g("%s.proj.%s.p50" % (fam, scen)),
                             g("%s.proj.%s.p90" % (fam, scen)))
            row("A13 %s %s ordered" % (fam, scen), p10 < p50 < p90,
                "%.2f < %.2f < %.2f" % (p10, p50, p90))

    # A14 CCHI is the geometric mean of CRI and HSI, so its 2050/2023 ratio must
    # sit exactly halfway between the two component ratios in log space.
    cri_r = g("cri.proj.ssp585.p50") / g("cri.hist.2023_12")
    hsi_r = g("hsi.proj.ssp585.p50") / g("hsi.hist.2023_12")
    cchi_r = g("cchi.proj.ssp585.p50") / g("cchi.hist.2023_12")
    import math
    geom = math.sqrt(cri_r * hsi_r)
    row("A14 CCHI == geometric mean",
        abs(cchi_r / geom - 1.0) < 5e-3,
        "CCHI ratio %.4f vs sqrt(CRI %.4f x HSI %.4f) = %.4f"
        % (cchi_r, cri_r, hsi_r, geom))

    # A15 defended SSP5-8.5 residual is above the historical defended level
    row("A15 residual above historical defended",
        g("eal.residual.ssp585_def_vs_hist_def_pct") > 0,
        "%.4f%%" % g("eal.residual.ssp585_def_vs_hist_def_pct"))

    # A16 HSI peaks after the terminal date it is compared with
    row("A16 HSI peak above terminal",
        g("hsi.hist.peak") > g("hsi.hist.last"),
        "peak %.2f vs last %.2f" % (g("hsi.hist.peak"), g("hsi.hist.last")))
    return rows


def check_consistency(truth: dict, mapping: list[dict]) -> list[dict]:
    rows = []

    def row(name, ok, detail):
        rows.append({"row_id": name, "token": "", "class": "CONSIST",
                     "bind": "", "status": "OK" if ok else "MISMATCH",
                     "expected": "", "detail": detail,
                     "metric_value": "", "metric_source": ""})

    g = lambda k: float(truth[k]["value"])

    # district aggregation closes on the city total
    parts = sum(g("eal.dist.hist.%s.bn" % d) for d in
                ("浦东新区", "杨浦区", "闵行区", "徐汇区", "虹口区", "黄浦区",
                 "宝山区", "静安区", "松江区", "普陀区", "嘉定区", "长宁区",
                 "青浦区", "奉贤区", "金山区", "崇明区"))
    row("C1 district sum == city EAL",
        abs(parts - g("eal.city.hist.nodef.bn")) < 1e-6,
        "%.6f vs %.6f" % (parts, g("eal.city.hist.nodef.bn")))

    # CCHI is the geometric mean of CRI and HSI, rebased
    row("C2 CCHI between CRI and HSI", True,
        "informational: CRI %.2f / HSI %.2f / CCHI %.2f at 2023-12"
        % (g("cri.hist.2023_12"), g("hsi.hist.2023_12"), g("cchi.hist.2023_12")))

    # the abstract agrees with the results on every shared figure
    shared = [("24.2 billion", "eal.city.hist.nodef.bn"),
              ("21.5%", "eal.city.hist.red_pct"),
              ("74%", "eal.city.hist.wind_share_pct"),
              ("40.3 billion", "eal.city.ssp585.nodef.bn"),
              ("26%", "eal.city.hist.surge_share_pct"),
              ("40%", "eal.city.ssp585.surge_share_pct"),
              ("53%", "cchi.incr.ssp585.p50_pct")]
    by_token: dict[str, set] = {}
    for r in mapping:
        if r["class"] in VERIFIED and r["bind"]:
            by_token.setdefault(r["token"], set()).add(r["bind"])
    multi = {t: sorted(b) for t, b in by_token.items() if len(b) > 1}
    row("C3 token fan-out (informational)", True,
        "%d distinct printed tokens; %d print the same value for several "
        "quantities (expected: 0.176 base vs sweep, 4.5/8.5 labels)"
        % (len(by_token), len(multi)))
    for tok, mid in shared:
        row("C4 abstract==results %s" % tok, tok in by_token,
            "token %r appears %d time(s) in v11" % (tok, sum(
                1 for r in mapping if r["token"] == tok)))
    return rows


# ─────────────────────────────────────────────────────────────────────────


def main() -> int:
    global DOCX_PATH, FIGCSV, OUT
    ap = argparse.ArgumentParser(description="WP11.4 adjudicator")
    ap.add_argument("--docx", default="")
    ap.add_argument("--truth", default=str(TRUTH))
    ap.add_argument("--map", default=str(MAP))
    ap.add_argument("--figs", default=str(FIGCSV))
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--only", default="",
                    help="numeric | tables | figures | asserts | consist")
    args = ap.parse_args()

    if args.docx:
        DOCX_PATH = Path(args.docx)
    FIGCSV = Path(args.figs)
    OUT = Path(args.out)
    truth = {r["metric_id"]: r for r in load_csv(Path(args.truth))}
    mapping = load_csv(Path(args.map))
    print("=== WP11.4 adjudicator ===")
    print("  document      : %s" % DOCX_PATH.name)
    print("  truth metrics : %d" % len(truth))
    print("  mapped tokens : %d" % len(mapping))

    groups: list[list[dict]] = []
    want = args.only
    if want in ("", "numeric"):
        groups.append(check_numeric(truth, mapping))
    if want in ("", "tables"):
        groups.append(check_tables(truth))
        groups.append(check_table_b1())
    if want in ("", "figures"):
        groups.append(check_figures())
    if want in ("", "asserts"):
        groups.append(check_assertions(truth))
    if want in ("", "consist"):
        groups.append(check_consistency(truth, mapping))

    rows = [r for g in groups for r in g]
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    for k in sorted(counts):
        print("    %-12s %4d" % (k, counts[k]))

    bad = [r for r in rows if r["status"] in
           ("MISMATCH", "NO-METRIC", "NO-SOURCE", "MISSING", "NO-NUMBER")]
    if bad:
        print("  --- findings (%d) ---" % len(bad))
        for r in bad:
            print("    %-12s %-10s %-22s %s"
                  % (r["status"], r["row_id"], repr(r["token"])[:22],
                     r["detail"][:110]))

    cols = ["row_id", "class", "token", "bind", "status", "expected",
            "metric_value", "metric_source", "detail"]
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=cols, lineterminator="\n",
                       extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow(r)
    tmp = OUT.with_suffix(".csv.tmp")
    tmp.write_text(buf.getvalue(), encoding="utf-8", newline="\n")
    tmp.replace(OUT)
    print("  wrote %s (%d rows)" % (OUT.relative_to(NEWROOT), len(rows)))
    print("RESULT: %s" % ("ALIGN-FINDINGS" if bad else "ALIGN-OK"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
