"""WP7.2 step 2: build the machine-readable v10 edit plan.

Inputs (read-only)
------------------
* ``docs/_数字变更对照表.md``   - the WP7.1 change table (single source of truth)
* ``docs/_数值清单.csv``        - per-location ``style`` / ``has_math`` flags
* ``docs/_Table8_WP6重算.md``   - Table 8 three-column old->new (human cross-check)

Outputs
-------
* ``docs/_v10_edit_plan.csv``   - one row per edit (the operative list)
* ``docs/_v10_edit_plan.md``    - human-readable, grouped by location

Key rule
--------
The change table stores *numeric* OLD/NEW.  The manuscript stores *printed*
tokens.  A CHANGE row therefore only produces a text edit when the newly
rounded value prints differently from the token already in the document
(e.g. ``24.2 billion`` 24.153 -> 24.204 stays ``24.2 billion``: NO-OP).
Rows whose OLD/NEW are strings (the Table-8 "band" rows) are handled as
literal replacements; if the literal is absent from the text they are
informational only.

Explicit override tables (auditable, kept in code):
  TABLE2_CELLS  - Table 2 rows 3/4 are swapped as whole rows (see errata)
  TABLE8_CELLS  - Table 8 edits precise to the column
  TEXT_EDITS    - pure-text edits (7 from the change table, 1 voided)
  WATCH_EDITS   - the one watch item promoted to an edit (P19 0.38 -> 0.39 permille)

Usage
-----
    & ".\\env\\run.ps1" tools\\make_edit_plan.py [--out-dir DIR] [--strict]
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

NEWROOT = Path(__file__).resolve().parent.parent
DOCS = NEWROOT / "docs"

CHANGE_TABLE = DOCS / "_数字变更对照表.md"
INVENTORY = DOCS / "_数值清单.csv"

MINUS = "\u2212"          # the manuscript uses U+2212 for negatives
PLUS = "+"

# ---------------------------------------------------------------------------
# Table 2 (loc id T1) - rows 3 and 4 are swapped as WHOLE ROWS: the district
# label and its three values travel together, because under the A baseline
# Minhang (2.2685 bn) outranks Xuhui (2.2211 bn).
# ---------------------------------------------------------------------------
TABLE2_CELLS = [
    ("T1#r1c1", "5.9",  "6.0",  "Pudong 5.9286 -> 5.9944 (1 dp)"),
    ("T1#r3c0", "Xuhui",  "Minhang", "row swap: A-baseline rank 3 = Minhang"),
    ("T1#r3c2", "4.1",  "8.0",  "row swap: Minhang exposure 8.0 T"),
    ("T1#r3c3", "0.56", "0.28", "row swap: Minhang ratio 0.2825 permille"),
    ("T1#r4c0", "Minhang", "Xuhui", "row swap: A-baseline rank 4 = Xuhui"),
    ("T1#r4c1", "2.3",  "2.2",  "row swap: Xuhui EAL 2.2211 bn"),
    ("T1#r4c2", "8.0",  "4.0",  "row swap: Xuhui exposure 3.98 T"),
    ("T1#r4c3", "0.28", "0.56", "row swap: Xuhui ratio 0.5575 permille"),
    ("T1#r5c3", "0.83", "0.82", "Hongkou 0.8266 -> 0.8214 permille"),
]

# ---------------------------------------------------------------------------
# Table 8 (loc id T8) - 0-based row indices as used by the extractor.
# n-th parameter row -> docx row: n<=10 -> n+1 ; 11<=n<=16 -> n+2 ; n=17 -> r20.
# Columns: c4 = Baseline value, c5 = Range of index, c6 = Max deviation.
# NOT edited on purpose: n=9 / r10 c6 (author ruling 16 keeps "0%"),
#                       n=12 / r14 c6 ("-1.8% to +1.1%" is format-only).
# ---------------------------------------------------------------------------
TABLE8_CELLS = [
    # --- Range of index (10 cells)
    ("T8#r3c5",  "21.1\u201328.1B", "21.1\u201328.2B", "TC V_half base scale range"),
    ("T8#r4c5",  "18.7\u201331.6B", "18.7\u201331.7B", "TC V_thresh range"),
    ("T8#r5c5",  "22.6\u201325.7B", "22.6\u201325.8B", "GAMMA_SVI range"),
    ("T8#r6c5",  "22.6\u201327.5B", "22.7\u201327.6B", "V_HALF_ADJ_A_old range"),
    ("T8#r7c5",  "23.1\u201326.4B", "23.1\u201326.5B", "V_HALF_ADJ_A_new range"),
    ("T8#r8c5",  "22.0\u201328.7B", "22.1\u201328.7B", "V_HALF_ADJ_B_old range"),
    ("T8#r13c5", "594\u2013610",    "596\u2013612",    "CRI_EWMA_ALPHA range"),
    ("T8#r14c5", "588\u2013606",    "590\u2013607",    "CRI_DAMAGE_KAPPA range"),
    ("T8#r17c5", "574\u2013631",    "576\u2013633",    "CFI_WEIGHT_SLA range"),
    ("T8#r20c5", "396\u2013399",    "397\u2013400",    "CFCI_TARGET_RHO range"),
    # --- Baseline value (3 cells)
    ("T8#r13c4", "599", "601", "CRI_EWMA_ALPHA baseline (CRI 600.874 -> 601)"),
    ("T8#r14c4", "599", "601", "CRI_DAMAGE_KAPPA baseline"),
    ("T8#r17c4", "599", "601", "CFI_WEIGHT_SLA baseline"),
    # --- Max deviation (4 cells; 2 of them author-ruled)
    ("T8#r5c6",  f"{MINUS}6.3% to +6.3%", f"{MINUS}6% to +6%",  "GAMMA_SVI max dev"),
    ("T8#r15c6", f"{MINUS}2.3% to +4.2%", f"{MINUS}2% to +4%",  "HP_LAMBDA max dev"),
    ("T8#r16c6", f"\u22480% to +2.6%",    f"{MINUS}0.1% to +2.6%", "VOLATILITY_WINDOW max dev [ruling 15]"),
    ("T8#r20c6", f"{MINUS}0.8% to \u22480%", f"{MINUS}0.2% to +0.6%", "CFCI_TARGET_RHO max dev [ruling 14]"),
]

# ---------------------------------------------------------------------------
# Pure-text edits.
#   * the change table lists 7; the T8#r8c0 item is VOIDED (the OMML symbols
#     are present in the XML - "fixing" it would duplicate V_half into literal
#     LaTeX text), so 6 remain, of which P194 needs 3 occurrences.
# ---------------------------------------------------------------------------
TEXT_EDITS = [
    ("T10#r8c2",  1, "fi_01_housing_stress_index.png", "fi_01_finance_risk_index.png",
     "stale figure filename in the figure index (WP5 rename)"),
    ("T10#r11c2", 1, "fi_04_hsi_vs_cri_overlay.png", "fi_04_fri_vs_cri_overlay.png",
     "stale figure filename in the figure index (WP5 rename)"),
    ("P24",       1, "Pudong, Yangpu, and Xuhui", "Pudong, Yangpu, and Minhang",
     "A-baseline top-3 contributors: Minhang replaces Xuhui"),
    ("P194",      1, "Lianjia", "Anjuke", "figure-1 caption / exposure source: url host is anjuke.com"),
    ("P194",      2, "Lianjia", "Anjuke", "occurrence 2 of 3"),
    ("P194",      3, "Lianjia", "Anjuke", "occurrence 3 of 3"),
    ("P204",      1, "Lianjia (Beike)", "Anjuke", "housing-market source: url host is anjuke.com"),
    ("P16",       1, "above the historical no-defence level", "above the historical defended level",
     "39.5% = 26.5185/19.0056-1, i.e. vs the historical DEFENDED residual"),
]

# The one `watch` item promoted to an edit (user instruction: align everything).
WATCH_EDITS = [
    ("P19", 1, "0.38\u2030", "0.39\u2030",
     "16-district mean EAL/exposure; both the old and the A baseline give 0.39"),
]

# Half-up rounding boundary cases: the registry value and the printed token
# disagree about the last digit, so the automatic rule (which only fires when
# the token is reproduced by the registry OLD value) cannot see them.
ROUND_BOUNDARY_CELLS = [
    ("T4#r2c1", "395", "394",
     "Table 5 SSP2-4.5 p10: registry OLD 394.50 prints 395 under half-up rounding "
     "while WP7.1 recorded OLD/NEW as 394/394; the A baseline is 393.73, which prints 394"),
]

VOIDED_ITEMS = [
    ("T8#r8c0", " adj. B_old", "NO-OP: the V_half symbol is an m:oMath object present in the XML; "
                               "inserting literal LaTeX would duplicate it"),
]

# ---------------------------------------------------------------------------
# formatting helpers
# ---------------------------------------------------------------------------
NUM_RE = re.compile(r"^[+-]?\d+(?:\.\d+)?$")


def is_number(s: str) -> bool:
    return bool(NUM_RE.match(s.strip().replace(MINUS, "-")))


def fmt_like(token: str, value: float) -> str:
    """Render ``value`` using the decimal count / separators / suffix of ``token``."""
    sign_pref = ""
    core = token
    if core.startswith("+"):
        sign_pref, core = PLUS, core[1:]
    elif core.startswith(MINUS):
        core = core[1:]
    elif core.startswith("-"):
        core = core[1:]
    m = re.match(r"^([\d,]*\.?\d*)(.*)$", core)
    if not m:
        raise ValueError("unparsable token %r" % token)
    numtxt, suffix = m.group(1), m.group(2)
    has_comma = "," in numtxt
    dec = len(numtxt.split(".")[1]) if "." in numtxt else 0
    q = Decimal(str(value)).quantize(Decimal(1).scaleb(-dec), rounding=ROUND_HALF_UP)
    body = f"{abs(q):,.{dec}f}" if has_comma else f"{abs(q):.{dec}f}"
    if q < 0:
        return MINUS + body + suffix
    if sign_pref == PLUS:
        return PLUS + body + suffix
    return body + suffix


# ---------------------------------------------------------------------------
# change-table parsing
# ---------------------------------------------------------------------------
SEC_RE = re.compile(r"^### (?:段落 )?(P\d+|T\d+#r\d+c\d+)\s*$")


def parse_change_table(path: Path):
    """Return list of dicts: loc, token, old_raw, new_raw, status, qty."""
    rows = []
    loc = None
    hdr_seen = False
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.rstrip()
        m = SEC_RE.match(line)
        if m:
            loc = m.group(1)
            hdr_seen = False
            continue
        if loc is None:
            continue
        if line.startswith("| token"):
            hdr_seen = True
            continue
        if not hdr_seen or not line.startswith("|"):
            continue
        if set(line.replace("|", "").strip()) <= set("-: "):
            continue
        parts = [p.strip() for p in line.strip().strip("|").split("|")]
        if len(parts) < 6:
            continue
        tok = parts[0].strip().strip("`")
        rows.append(dict(loc=loc, token=tok, old_raw=parts[1], new_raw=parts[2],
                         status=parts[3], qty=parts[4]))
    return rows


def load_has_math(path: Path) -> dict[str, bool]:
    out = {}
    if not path.exists():
        return out
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            ident = r["ID"]
            cur = "True" in (r.get("has_math") or "")
            out[ident] = out.get(ident, False) or cur
    return out


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description="build the v10 edit plan")
    ap.add_argument("--change-table", default=str(CHANGE_TABLE))
    ap.add_argument("--inventory", default=str(INVENTORY))
    ap.add_argument("--out-dir", default=str(DOCS))
    ap.add_argument("--strict", action="store_true",
                    help="fail when printed OLD token does not reproduce the token")
    args = ap.parse_args()

    ct = Path(args.change_table)
    if not ct.exists():
        print("ERROR change table not found: %s" % ct)
        return 2
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    parsed = parse_change_table(ct)
    has_math = load_has_math(Path(args.inventory))
    print("parsed %d location rows from %s" % (len(parsed), ct.name))

    edits = []
    counts = {"CHANGE": 0, "same": 0, "watch": 0, "other": 0}
    noop_precision = []
    warn_align = []
    info_only = []
    misaligned_same = []

    for row in parsed:
        status = row["status"]
        if status in counts:
            counts[status] += 1
        else:
            counts["other"] += 1
        if status not in ("CHANGE", "same"):
            continue
        tok, old_raw, new_raw = row["token"], row["old_raw"], row["new_raw"]
        if is_number(old_raw) and is_number(new_raw):
            old_v = float(old_raw.replace(MINUS, "-"))
            new_v = float(new_raw.replace(MINUS, "-"))
            printed_old = fmt_like(tok, old_v)
            printed_new = fmt_like(tok, new_v)
            aligned = (printed_old == tok)
            if status == "CHANGE" and not aligned:
                warn_align.append((row["loc"], tok, printed_old, row["qty"]))
            if not aligned:
                # the registry row is not the printed form of this token: ignore
                if status == "same":
                    misaligned_same.append((row["loc"], tok, printed_old, printed_new, row["qty"]))
                continue
            if printed_new == tok:
                if status == "CHANGE":
                    noop_precision.append((row["loc"], tok, new_v, row["qty"]))
                continue
            # the printed form changes
            cat = "NUMERIC" if status == "CHANGE" else "ROUND-BOUNDARY"
            note = row["qty"] if status == "CHANGE" else \
                "对标表判 same（数值近乎不变），但四舍五入后印刷值由 %s 变 %s" % (tok, printed_new)
            edits.append(dict(loc=row["loc"], occurrence=1, old_text=tok,
                              new_text=printed_new, item_id="", category=cat,
                              note=note))
        elif status == "CHANGE":
            # band-style row: literal replacement if the OLD string is in the text
            if old_raw and new_raw and old_raw != new_raw:
                edits.append(dict(loc=row["loc"], occurrence=1, old_text=old_raw,
                                  new_text=new_raw, item_id="", category="BAND",
                                  note=row["qty"]))
            else:
                info_only.append((row["loc"], tok, old_raw, new_raw, row["qty"]))

    # --- drop the locations handled by explicit overrides
    override_locs = {c[0] for c in TABLE2_CELLS} | {c[0] for c in TABLE8_CELLS}
    override_prefix = {"T1#", "T8#"}          # whole-table overrides
    auto_dropped = [e for e in edits
                    if e["loc"] in override_locs or any(e["loc"].startswith(p) for p in override_prefix)]
    edits = [e for e in edits
             if not (e["loc"] in override_locs or any(e["loc"].startswith(p) for p in override_prefix))]

    for loc, old, new, note in TABLE2_CELLS:
        edits.append(dict(loc=loc, occurrence=1, old_text=old, new_text=new,
                          item_id="TB2", category="TABLE2-SWAP", note=note))
    for loc, old, new, note in TABLE8_CELLS:
        edits.append(dict(loc=loc, occurrence=1, old_text=old, new_text=new,
                          item_id="TB8", category="TABLE8", note=note))
    for loc, occ, old, new, note in TEXT_EDITS:
        edits.append(dict(loc=loc, occurrence=occ, old_text=old, new_text=new,
                          item_id="TEXT", category="TEXT", note=note))
    for loc, occ, old, new, note in WATCH_EDITS:
        edits.append(dict(loc=loc, occurrence=occ, old_text=old, new_text=new,
                          item_id="WATCH", category="WATCH-PROMOTED", note=note))
    for loc, old, new, note in ROUND_BOUNDARY_CELLS:
        edits.append(dict(loc=loc, occurrence=1, old_text=old, new_text=new,
                          item_id="ROUND", category="ROUND-BOUNDARY", note=note))

    # --- resolve has_math per location
    for e in edits:
        e["has_math"] = has_math.get(e["loc"], False)

    # --- duplicate (loc, old_text) handling: sequence the occurrence numbers
    seen: dict[tuple[str, str], int] = {}
    for e in edits:
        key = (e["loc"], e["old_text"])
        if key in seen:
            seen[key] += 1
            if e["category"] != "TEXT":       # explicit TEXT rows already carry occurrences
                e["occurrence"] = seen[key]
        else:
            seen[key] = 1

    # --- dedupe identical (loc, occurrence)
    final, dedup = [], set()
    for e in edits:
        k = (e["loc"], e["occurrence"], e["old_text"], e["new_text"])
        if k in dedup:
            continue
        dedup.add(k)
        final.append(e)
    final.sort(key=lambda e: (e["loc"].startswith("T"), _loc_key(e["loc"]), e["occurrence"]))

    for i, e in enumerate(final, 1):
        e["seq"] = i

    # --- write CSV
    csv_path = out_dir / "_v10_edit_plan.csv"
    cols = ["seq", "loc_kind", "loc_id", "occurrence", "old_text", "new_text",
            "item_id", "category", "has_math", "note"]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for e in final:
            w.writerow({
                "seq": e["seq"],
                "loc_kind": "paragraph" if e["loc"].startswith("P") else "table_cell",
                "loc_id": e["loc"],
                "occurrence": e["occurrence"],
                "old_text": e["old_text"],
                "new_text": e["new_text"],
                "item_id": e["item_id"],
                "category": e["category"],
                "has_math": e["has_math"],
                "note": e["note"],
            })

    # --- write markdown
    md_path = out_dir / "_v10_edit_plan.md"
    by_loc: dict[str, list[dict]] = {}
    for e in final:
        by_loc.setdefault(e["loc"], []).append(e)
    lines = []
    lines.append("# v10 改稿执行清单（WP7.2）\n")
    lines.append("- 生成器：`tools/make_edit_plan.py`")
    lines.append("- 来源：`docs/_数字变更对照表.md`（自动解析）+ 4 张显式 override 表（代码内）")
    lines.append("- 机器可读版：`docs/_v10_edit_plan.csv`（**改写工具只认这个**）")
    lines.append("")
    lines.append("## 摘要\n")
    lines.append("| 项 | 数 |")
    lines.append("|---|---:|")
    lines.append("| 对照表条目 | %d |" % len(parsed))
    lines.append("| 　CHANGE | %d |" % counts["CHANGE"])
    lines.append("| 　same | %d |" % counts["same"])
    lines.append("| 　watch | %d |" % counts["watch"])
    lines.append("| CHANGE 中因精度未变而 **无需改字** | %d |" % len(noop_precision))
    lines.append("| CHANGE 中被表级 override 接管 | %d |" % len(auto_dropped))
    lines.append("| band 型仅作说明（文中无该串） | %d |" % len(info_only))
    lines.append("| **最终编辑行数** | **%d** |" % len(final))
    for cat in ("NUMERIC", "ROUND-BOUNDARY", "BAND", "TABLE2-SWAP", "TABLE8", "TEXT",
                "WATCH-PROMOTED"):
        n = sum(1 for e in final if e["category"] == cat)
        if n:
            lines.append("| 　%s | %d |" % (cat, n))
    lines.append("")
    if misaligned_same:
        lines.append("## `same` 行中 token 与登记值不对应（判为登记错位，不改）\n")
        lines.append("| 位置 | token | 由 OLD 复算 | 由 NEW 复算 | 量 |")
        lines.append("|---|---|---|---|---|")
        for loc, tok, po, pn, qty in misaligned_same:
            lines.append("| `%s` | `%s` | `%s` | `%s` | %s |" % (loc, tok, po, pn, qty))
        lines.append("")
    if VOIDED_ITEMS:
        lines.append("## 作废条目（不执行）\n")
        for loc, txt, why in VOIDED_ITEMS:
            lines.append("- `%s` 原提议 `%s` — **%s**" % (loc, txt.strip(), why))
        lines.append("")
    if warn_align:
        lines.append("## 对齐告警（token 无法由 OLD 值复现，需人工确认）\n")
        lines.append("| 位置 | token | 由 OLD 复算 | 量 |")
        lines.append("|---|---|---|---|")
        for loc, tok, po, qty in warn_align:
            lines.append("| `%s` | `%s` | `%s` | %s |" % (loc, tok, po, qty))
        lines.append("")
    if noop_precision:
        lines.append("## 精度未变（CHANGE 但不用改字）\n")
        lines.append("| 位置 | token | NEW | 量 |")
        lines.append("|---|---|---:|---|")
        for loc, tok, nv, qty in noop_precision:
            lines.append("| `%s` | `%s` | %s | %s |" % (loc, tok, nv, qty))
        lines.append("")
    lines.append("## 逐位置编辑\n")
    for loc in sorted(by_loc, key=_loc_key):
        rows = by_loc[loc]
        hm = "（含公式，严格单 run）" if rows[0]["has_math"] else ""
        lines.append("### `%s` %s\n" % (loc, hm))
        lines.append("| # | 序 | OLD | NEW | 类别 | 说明 |")
        lines.append("|---:|---:|---|---|---|---|")
        for r in rows:
            lines.append("| %d | %d | `%s` | `%s` | %s | %s |" %
                         (r["occurrence"], r["seq"], r["old_text"], r["new_text"],
                          r["category"], r["note"].replace("|", "/")))
        lines.append("")
    md_path.write_text("\n".join(lines), encoding="utf-8")

    print("")
    print("=== SUMMARY ===")
    print("  parsed rows      : %d" % len(parsed))
    print("  CHANGE/same/watch: %d / %d / %d (other %d)" %
          (counts["CHANGE"], counts["same"], counts["watch"], counts["other"]))
    print("  precision NO-OP  : %d" % len(noop_precision))
    print("  override-taken   : %d (auto rows dropped)" % len(auto_dropped))
    print("  info-only bands  : %d" % len(info_only))
    print("  misaligned same  : %d (registry value is not the printed token)" % len(misaligned_same))
    print("  FINAL EDITS      : %d" % len(final))
    for cat in ("NUMERIC", "ROUND-BOUNDARY", "BAND", "TABLE2-SWAP", "TABLE8", "TEXT",
                "WATCH-PROMOTED"):
        n = sum(1 for e in final if e["category"] == cat)
        print("    %-14s : %d" % (cat, n))
    print("")
    print("  wrote %s" % csv_path)
    print("  wrote %s" % md_path)
    if warn_align:
        print("")
        print("  [!] %d alignment warnings (token not reproducible from OLD):" % len(warn_align))
        for loc, tok, po, qty in warn_align:
            print("      %-12s token=%-10s from-OLD=%-10s  %s" % (loc, tok, po, qty))
        if args.strict:
            print("RESULT: FAIL (alignment warnings, strict)")
            return 3
    print("RESULT: OK")
    return 0


def _loc_key(loc: str):
    m = re.match(r"^P(\d+)$", loc)
    if m:
        return (0, int(m.group(1)), 0, 0)
    m = re.match(r"^T(\d+)#r(\d+)c(\d+)$", loc)
    if m:
        return (1, int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return (2, 0, 0, 0)


if __name__ == "__main__":
    sys.exit(main())
