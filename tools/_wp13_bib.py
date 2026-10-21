# -*- coding: utf-8 -*-
"""WP13.4 - bibliography verification: 59 entries, 49 DOIs, citation closure.

The reference list carries 370 numeric tokens (years, volumes, issues, pages,
article numbers, DOI fragments).  They are not model outputs, so they cannot be
checked against the truth table - but they can be checked against the publisher
record, which is what this module does:

  * every entry is parsed into author / year / container / volume / pages / DOI;
  * every DOI is resolved against Crossref and, failing that, DataCite, and the
    returned year, volume, pages and first author are compared with the printed
    entry;
  * entries without a DOI (reports, working papers, web pages) fall back to a
    structural check plus a citation check;
  * citation closure runs both ways: every in-text citation must have an entry,
    and every entry must be cited.

Results are cached in docs\\_wp13_doi_cache.json so re-runs are offline-fast and
repeatable; delete the cache to force a refresh.

OUTPUT
    docs\\_wp13_文献核验.csv
    docs\\_wp13_文献摘要.json

USAGE
    env\\run.ps1 tools\\_wp13_bib.py
    env\\run.ps1 tools\\_wp13_bib.py --offline      # cache only, no network
    env\\run.ps1 tools\\_wp13_bib.py --refresh      # ignore the cache
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
import xml.etree.ElementTree as ET

NEWROOT = Path(__file__).resolve().parent.parent
DOCS = NEWROOT / "docs"
DOCX = NEWROOT / "manuscript" / "PAPER_MANUSCRIPT_v12.docx"
MAPPING = DOCS / "_wp11_v12映射表.csv"
OUT = DOCS / "_wp13_文献核验.csv"
OUT_SUM = DOCS / "_wp13_文献摘要.json"
CACHE = DOCS / "_wp13_doi_cache.json"

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
UA = "dsh-wp13-audit/1.0 (manuscript numeric audit; contact: author)"

DOI_RE = re.compile(r"10\.\d{4,9}/[^\s,;)\]]+")


def load_csv(p: Path) -> list[dict]:
    with io.open(p, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", s.lower())


def doc_paras(docx: Path) -> list[tuple[str, str, str]]:
    with zipfile.ZipFile(docx) as zf:
        root = ET.fromstring(zf.read("word/document.xml"))
    body = root.find(W + "body")
    out = []
    i = 0
    for child in body:
        if child.tag != W + "p":
            continue
        st = child.find(W + "pPr/" + W + "pStyle")
        st = st.get(W + "val") if st is not None else ""
        txt = "".join(t.text or "" for t in child.iter(W + "t"))
        out.append(("P%d" % i, st, txt))
        i += 1
    return out


# ───────────────────────────────────────────────────────────── entry parsing
ORG_YEAR = re.compile(r"\((\d{4})[a-z]?\)")


def parse_entry(pid: str, txt: str) -> dict:
    t = txt.strip()
    y = ORG_YEAR.search(t)
    year = y.group(1) if y else ""
    head = t[:y.start()].strip() if y else t
    head = head.rstrip(", ").strip()
    # A personal author list always starts "Surname, I."; anything else is an
    # organisation ("NOAA National Centers for Environmental Information (2022)")
    first = re.split(r" and |,", head)[0].strip()
    personal = bool(re.match(r"^[A-Z][\w\u2019'\-]+\s*,\s*[A-Z]\.", head))
    acro = re.search(r"\(([A-Z]{2,8})\)", head)
    if personal:
        surname = first.split()[-1]
    elif acro:
        surname = acro.group(1)
    else:
        surname = head.split()[0] if head else ""
    entry = {"row_id": pid, "text": t, "year": year, "surname": surname,
             "personal": personal, "author_head": head[:80], "doi": "",
             "volume": "", "pages": "", "issue": "", "container": "",
             "book_chapter": bool(re.search(r"\.\s+In\s+[A-Z]|In:\s", t))}
    # DOI: take everything after a doi.org link, then trim sentence punctuation
    m = re.search(r"doi\.org/(\S+)", t)
    if m:
        entry["doi"] = m.group(1).rstrip(".").rstrip(")").rstrip(",")
    # container / volume(issue), pages  ->  "Journal, 12(7), 3085-3097."
    m = re.search(r",\s*(\d{1,4})\s*(?:\((\d{1,3})\))?\s*,\s*"
                  r"([A-Za-z]?\d+\s*[\u2013\-]\s*[A-Za-z]?\d+|[A-Za-z]?\d+)\s*\.",
                  t)
    if m:
        entry["volume"], entry["issue"], entry["pages"] = (
            m.group(1), m.group(2) or "", m.group(3))
    m2 = re.search(r"\.\s*([^.]{3,80}?),\s*\d{1,4}\s*(?:\(\d+\))?", t)
    if m2:
        entry["container"] = m2.group(1).strip()
    return entry


# ───────────────────────────────────────────────────────────────── resolvers
def fetch_json(url: str, timeout: int = 25):
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def resolve_crossref(doi: str):
    url = "https://api.crossref.org/works/" + urllib.parse.quote(doi, safe="")
    d = fetch_json(url)["message"]
    authors = d.get("author") or []
    fam = authors[0].get("family", "") if authors else ""
    issued = (d.get("issued") or {}).get("date-parts") or [[""]]
    return {"source": "crossref", "title": (d.get("title") or [""])[0],
            "year": str(issued[0][0]) if issued and issued[0] else "",
            "first_author": fam, "volume": str(d.get("volume", "") or ""),
            "page": str(d.get("page", "") or ""),
            "container": (d.get("container-title") or [""])[0]}


def resolve_datacite(doi: str):
    url = "https://api.datacite.org/dois/" + urllib.parse.quote(doi, safe="")
    d = fetch_json(url)["data"]["attributes"]
    creators = d.get("creators") or []
    fam = ""
    if creators:
        fam = creators[0].get("familyName") or creators[0].get("name", "").split(",")[0]
    return {"source": "datacite", "title": (d.get("titles") or [{}])[0].get("title", ""),
            "year": str(d.get("publicationYear", "") or ""),
            "first_author": fam, "volume": "", "page": "",
            "container": (d.get("publisher") or "")}


def resolve(doi: str, cache: dict, offline: bool, refresh: bool):
    if not refresh and doi in cache:
        return cache[doi]
    if offline:
        return {"error": "offline (no cache entry)"}
    for fn in (resolve_crossref, resolve_datacite):
        try:
            rec = fn(doi)
            cache[doi] = rec
            return rec
        except urllib.error.HTTPError as e:
            last = {"error": "HTTP %d" % e.code}
        except Exception as e:  # noqa: BLE001
            last = {"error": "%s: %s" % (type(e).__name__, e)}
    cache[doi] = last
    return last


def extract_cites(text: str) -> set[tuple[str, str]]:
    """(normalised first-author, year) pairs from parenthetical citations.

    Handles "(Bakkensen and Barrage, 2017)", "(Nicholls et al., 2008;
    Hallegatte et al., 2013)", "(USDA, 1986)" and "Wahl et al. (2015)".
    """
    out: set[tuple[str, str]] = set()
    NAME = r"[A-Z][\w\u2019'\u2013\-]+"
    for grp in re.findall(r"\(([^()]{0,180})\)", text):
        if not re.search(r"(?:19|20)\d{2}", grp):
            continue
        for seg in grp.split(";"):
            m = re.match(r"\s*(%s)[^,]{0,50}?,\s*((?:19|20)\d{2})" % NAME, seg)
            if m:
                out.add((norm(m.group(1)), m.group(2)))
                continue
            m = re.match(r"\s*(%s)\s+(?:et al\.?)?\s*,?\s*((?:19|20)\d{2})" % NAME, seg)
            if m:
                out.add((norm(m.group(1)), m.group(2)))
    for m in re.finditer(r"(%s)\s+(?:et al\.?)?\s*\(((?:19|20)\d{2})\)" % NAME, text):
        out.add((norm(m.group(1)), m.group(2)))
    return out


# ─────────────────────────────────────────────────────────────── comparisons
def cmp_field(name: str, printed: str, resolved: str,
              book_chapter: bool = False) -> tuple[str, str]:
    if not resolved:
        return "NA", "%s not returned" % name
    if not printed:
        return "NOTE", "%s only in the record: %r" % (name, resolved)
    a = norm(printed) if name != "year" else printed.strip()
    b = norm(resolved) if name != "year" else str(resolved).strip()
    if a == b:
        return "OK", "%s %r" % (name, printed)
    if name == "pages":
        pa = re.findall(r"\d+", printed)
        pb = re.findall(r"\d+", str(resolved))
        if pa and pb and pa[0] == pb[0]:
            return "OK", "pages start %s (%r vs %r)" % (pa[0], printed, resolved)
    if name == "year" and a and b:
        gap = abs(int(a) - int(b))
        if gap == 1 or (gap == 2 and book_chapter):
            return "MINOR", "year %s vs record %s" % (printed, resolved)
    return "FAIL", "%s printed %r vs record %r" % (name, printed, resolved)


def main() -> int:
    ap = argparse.ArgumentParser(description="WP13.4 bibliography verifier")
    ap.add_argument("--docx", default=str(DOCX))
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--sum", default=str(OUT_SUM))
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--sleep", type=float, default=0.15)
    args = ap.parse_args()

    paras = doc_paras(Path(args.docx))
    # locate the References block
    start = end = None
    for i, (pid, st, txt) in enumerate(paras):
        if st in ("1", "2") and txt.strip().lower().startswith("references"):
            start = i + 1
        elif start is not None and st in ("1", "2") and txt.strip():
            end = i
            break
    end = end or len(paras)
    ref_paras = [(pid, txt) for pid, st, txt in paras[start:end] if txt.strip()]
    entries = [parse_entry(pid, txt) for pid, txt in ref_paras]

    cache = {}
    if CACHE.is_file() and not args.refresh:
        cache = json.loads(CACHE.read_text(encoding="utf-8"))

    rows = []
    tally = {}
    for e in entries:
        verdict, notes = "", []
        if e["doi"]:
            rec = resolve(e["doi"], cache, args.offline, args.refresh)
            if args.sleep and not args.offline:
                time.sleep(args.sleep)
            if "error" in rec:
                verdict = "NO-RESOLVE"
                notes.append(rec["error"])
            else:
                checks = [
                    cmp_field("year", e["year"], rec.get("year", ""),
                              e["book_chapter"]),
                    cmp_field("volume", e["volume"], rec.get("volume", "")),
                    cmp_field("pages", e["pages"], rec.get("page", "")),
                ]
                # DataCite creator fields are unreliable (surname/given swapped),
                # so the author is only compared against a Crossref record
                if rec.get("source") == "crossref" and e["personal"]:
                    checks.append(cmp_field("author", e["surname"],
                                            rec.get("first_author", "")))
                static = [c for c in checks if c[0] == "FAIL"]
                minor = [c for c in checks if c[0] == "MINOR"]
                notes.extend("%s: %s" % (c[0], c[1]) for c in checks
                             if c[0] in ("OK", "MINOR", "FAIL"))
                notes.append("record: %s | %s %s" % (rec.get("source"),
                                                     rec.get("title", "")[:70],
                                                     rec.get("year", "")))
                verdict = ("MISMATCH" if static else
                           ("OK-BIB-DOI-MINOR" if minor else "OK-BIB-DOI"))
        else:
            well_formed = bool(e["surname"] and e["year"])
            verdict = "OK-BIB-STRUCT" if well_formed else "MISMATCH"
            notes.append("no DOI: structural check only (report / working paper / web)")
        rows.append({"row_id": e["row_id"], "kind": "reference",
                     "surname": e["surname"], "year": e["year"], "doi": e["doi"],
                     "verdict": verdict, "detail": " ; ".join(notes)[:400]})
        tally[verdict] = tally.get(verdict, 0) + 1

    CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1) + "\n",
                     encoding="utf-8", newline="\n")

    # ── citation closure: in-text -> entry, and entry -> in-text
    ref_ids = {(pid, txt) for pid, txt in ref_paras}
    body = [(pid, txt) for pid, st, txt in paras
            if (pid, txt) not in ref_ids and txt.strip()]
    body_text = " ".join(t for _, t in body)
    cites = extract_cites(body_text)

    uncited = []
    for e in entries:
        pat = re.escape(e["surname"].split("-")[0])
        if not re.search(pat + r".{0,80}?" + re.escape(e["year"]), body_text, re.I):
            uncited.append("%s %s" % (e["surname"], e["year"]))
    MONTHS = {"january", "february", "march", "april", "may", "june", "july",
              "august", "september", "october", "november", "december"}
    unmatched = []
    for name, year in sorted(cites):
        if name in MONTHS:
            continue
        ok = any(e["year"] == year and
                 (norm(e["surname"]) == name
                  or name.startswith(norm(e["surname"]))
                  or name in norm(e["author_head"]))
                 for e in entries)
        if not ok:
            unmatched.append((name, year))

    print("=== WP13.4 bibliography verifier ===")
    print("  document   : %s" % Path(args.docx).name)
    print("  entries    : %d (with DOI %d)" % (len(entries),
                                               sum(1 for e in entries if e["doi"])))
    print("  verdicts   : %s" % ", ".join("%s=%d" % kv for kv in sorted(tally.items())))
    print("  citations  : %d in-text (surname, year) pairs" % len(cites))
    print("  unmatched  : %s" % (unmatched[:8] or "none"))
    print("  uncited    : %s" % (uncited[:8] or "none"))
    bad = [r for r in rows if r["verdict"] in ("MISMATCH", "NO-RESOLVE")]
    if bad:
        print("  --- FINDINGS (%d) ---" % len(bad))
        for r in bad:
            print("    %-12s %-6s %-4s %-40s %s"
                  % (r["verdict"], r["row_id"], r["year"], r["doi"][:40],
                     r["detail"][:90]))

    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=["row_id", "kind", "surname", "year",
                                        "doi", "verdict", "detail"],
                       lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow(r)
    tmp = Path(args.out).with_suffix(".csv.tmp")
    tmp.write_text(buf.getvalue(), encoding="utf-8", newline="\n")
    tmp.replace(Path(args.out))

    summary = {
        "generated": __import__("datetime").datetime.now().isoformat(
            timespec="seconds"),
        "docx": Path(args.docx).name,
        "entries": len(entries),
        "with_doi": sum(1 for e in entries if e["doi"]),
        "verdicts": tally,
        "citations": len(cites),
        "unmatched_citations": unmatched,
        "uncited_entries": uncited,
        "findings": [r for r in rows if r["verdict"] in ("MISMATCH", "NO-RESOLVE")],
        "result": ("BIB-OK" if not bad and not unmatched else "BIB-FINDINGS"),
    }
    Path(args.sum).write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
                              encoding="utf-8", newline="\n")
    print("  wrote %s" % Path(args.out).relative_to(NEWROOT))
    print("  wrote %s" % Path(args.sum).relative_to(NEWROOT))
    print("RESULT: %s" % summary["result"])
    return 0 if summary["result"] == "BIB-OK" else 1


if __name__ == "__main__":
    sys.exit(main())
