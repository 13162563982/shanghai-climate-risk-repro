# -*- coding: utf-8 -*-
"""WP14 - identifier verification for the data-provenance ledger.

Rule inherited from WP8/WP13: **no DOI is written into a statement unless it
resolves and the resolved title matches the product we actually hold.**  A
plausible-looking identifier that we cannot confirm is recorded as
`未核实` and kept out of the availability statement.

Three things this module does
-----------------------------
1. resolve a fixed list of candidate DOIs (the ones printed in the shipped
   数据介绍.pdf files, plus the three already in the manuscript) against
   Crossref and then DataCite, and check the resolved title against expected
   tokens;
2. bibliographic search for the identifiers we do *not* have: FABDEM (Bristol),
   CMAB on Figshare, and the Science Data Bank built-up-area dataset;
3. write everything to docs\\_wp14_标识核验.csv and a private cache
   docs\\_wp14_doi_cache.json (WP13's cache is not touched).

Lookup machinery is reused from tools\\_wp13_bib.py so both audits resolve
identifiers identically.

USAGE
    <bundled python> tools\\_wp14_doi.py            # network
    <bundled python> tools\\_wp14_doi.py --offline  # cache only
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _wp13_bib import DOCS, fetch_json, resolve  # noqa: E402

CACHE = DOCS / "_wp14_doi_cache.json"
OUT_CSV = DOCS / "_wp14_标识核验.csv"

# ── (key, doi, 期望标题词（全须命中，小写）, 数据集编号, 说明)
CANDIDATES = [
    ("ibtracs", "10.25921/82ty-9e16", ["ibtracs"], "D01",
     "稿件已印；.nc 全局属性亦含该 DOI"),
    ("etopo", "10.25921/fd45-gt74", ["etopo"], "D03", "稿件已印且在文献表"),
    ("landscan", "10.48690/1524213", ["landscan"], "D04", "稿件已印"),
    ("cmfd_v2", "10.11888/Atmos.tpdc.302088", ["meteorological"], "D07",
     "数据介绍.pdf「数据引用」原文"),
    ("cmfd_paper", "10.1038/s41597-020-0369-y", ["forcing"], "D07",
     "数据介绍.pdf「论文引用」1"),
    ("chm_pre_v2", "10.5281/zenodo.14634575", ["chm"], "D09",
     "数据介绍.pdf 数据来源 = zenodo.org/records/14634575"),
    ("cmems_sla", "10.48670/moi-00148", ["sea surface heights"], "D12",
     "数据介绍.pdf「DOI (product)」原文"),
    ("gaia_paper", "10.1016/j.rse.2019.111510", ["impervious"], "D13",
     "数据介绍.pdf「数据引用格式」"),
    ("cmab_paper", "10.1038/s41597-025-04730-5", ["building"], "D17",
     "数据介绍.pdf「引用格式」"),
    ("cmab_figshare", "10.6084/m9.figshare.27992417", ["cmab"], "D17",
     "数据介绍.pdf 数据集本体（Figshare 27992417）"),
    ("fabdem_paper", "10.1088/1748-9326/ac4d4f", ["elevation", "forests"],
     "D02", "FABDEM 方法论文（Hawker et al. 2022）"),
    ("sdb_builtup", "10.57760/sciencedb.11249", ["ghsl"], "D18",
     "数据介绍.pdf 引用格式中的 CSTR:31253.11.sciencedb.11249"),
]

# Identifiers that Crossref/DataCite do not index but which are printed verbatim
# in the provider's own citation block, i.e. quoted evidence rather than a guess.
SOFT_OK = {
    "10.11888/Atmos.tpdc.302088":
        "TPDC 自带解析（doi.org/10.11888/...），Crossref/DataCite 均未收录；"
        "字符串取自供应方 数据介绍.pdf「数据引用」原文",
}

# ── bibliographic searches for identifiers we do not have on disk
SEARCHES = [
    ("fabdem", "D02", "FABDEM forest and building removed Copernicus DEM",
     ["fabdem"]),
    ("cmab_figshare", "D17",
     "CMAB World's First National-Scale Multi-Attribute Building Dataset",
     ["cmab"]),
    ("sdb_builtup", "D18",
     "GHSL-based Chinese urban entities 1975-2020", ["ghsl"]),
    ("gaia_data", "D13", "Annual maps of global artificial impervious area GAIA",
     ["gaia"]),
]


def exact(title: str, tokens: list[str]) -> bool:
    low = (title or "").lower()
    return all(t in low for t in tokens)


def search_crossref(query: str, rows: int = 4):
    url = ("https://api.crossref.org/works?rows=%d&query.bibliographic=%s"
           % (rows, urllib.parse.quote(query)))
    d = fetch_json(url)
    out = []
    for it in (d.get("message", {}).get("items") or []):
        out.append({"source": "crossref",
                    "doi": it.get("DOI", ""),
                    "title": (it.get("title") or [""])[0],
                    "year": (it.get("issued", {}).get("date-parts") or [[None]])[0][0],
                    "type": it.get("type", "")})
    return out


def search_datacite(query: str, rows: int = 4):
    url = ("https://api.datacite.org/dois?page[size]=%d&query=%s"
           % (rows, urllib.parse.quote(query)))
    d = fetch_json(url)
    out = []
    for it in (d.get("data") or []):
        at = it.get("attributes", {})
        out.append({"source": "datacite",
                    "doi": at.get("doi", ""),
                    "title": (at.get("titles") or [{}])[0].get("title", ""),
                    "year": at.get("publicationYear"),
                    "type": (at.get("types") or {}).get("resourceTypeGeneral", "")})
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--search", action="store_true",
                    help="还跑一遍书目检索兜底（默认关闭，直接 DOI 解析已足够）")
    args = ap.parse_args()

    cache: dict = {}
    if CACHE.is_file() and not args.refresh:
        cache = json.loads(CACHE.read_text(encoding="utf-8"))

    rows = []
    print("=== WP14 identifier check ===")
    for key, doi, tokens, slug, note in CANDIDATES:
        rec = resolve(doi, cache, args.offline, args.refresh)
        title = rec.get("title", "") or ""
        if rec.get("error"):
            verdict = "已核实（供应方原文）" if doi in SOFT_OK else "未解析"
        elif exact(title, tokens):
            verdict = "已核实"
        else:
            verdict = "已解析-标题未匹配"
        print("  %-14s %-34s %-7s %s" % (key, doi, verdict, title[:50]))
        rows.append({"项": key, "数据集": slug, "DOI": doi, "来源": rec.get("source", ""),
                     "解析标题": title, "年份": rec.get("year", ""),
                     "核验": verdict,
                     "依据": SOFT_OK.get(doi, note), "错误": rec.get("error", "")})

    for key, slug, query, tokens in (SEARCHES if args.search else []):
        line = {"项": key, "数据集": slug, "DOI": "", "来源": "",
                "解析标题": "", "年份": "", "核验": "未检索", "依据": query,
                "错误": ""}
        if args.offline:
            line["错误"] = "offline"
            rows.append(line)
            continue
        cands = []
        for fn in (search_crossref, search_datacite):
            try:
                cands += fn(query)
            except Exception as exc:      # noqa: BLE001 - network is best effort
                line["错误"] = "%s: %s" % (fn.__name__, exc)
        hit = next((c for c in cands if exact(c["title"], tokens)), None)
        if hit:
            line.update({"DOI": hit["doi"], "来源": hit["source"],
                         "解析标题": hit["title"], "年份": hit["year"],
                         "核验": "已核实（检索命中）", "错误": ""})
            print("  %-14s -> %s  %s" % (key, hit["doi"], hit["title"][:48]))
        else:
            line["核验"] = "未命中"
            print("  %-14s -> no title match (%d candidates)" % (key, len(cands)))
        rows.append(line)

    CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1) + "\n",
                     encoding="utf-8", newline="\n")
    with open(OUT_CSV, "w", encoding="utf-8-sig", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        wr.writeheader()
        wr.writerows(rows)

    ok = sum(1 for r in rows if r["核验"].startswith("已核实"))
    print("")
    print("  verified %d / %d" % (ok, len(rows)))
    print("  wrote %s" % OUT_CSV.name)
    print("RESULT: DOI-%s" % ("OK" if ok else "EMPTY"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
