# -*- coding: utf-8 -*-
"""WP11.0 - freeze the alignment-audit baseline.

WHAT IT DOES
------------
Records SHA256 / byte size / mtime for every artefact the WP11 audit depends on,
under seven roles, and asserts the docx hashes that must not drift:

    manuscript   PAPER_MANUSCRIPT_{FINAL,v10,v11}.docx  (+ expected SHA constants)
    output       the 20 model-output files that feed the manuscript numbers
    figure       manuscript/figures/*.png (41) + the figure generators
    config       00_config.py (Climate / Finance / Composite) + sweep spec
    log          the run logs of the last full pipeline execution
    input        pinned data inputs (IBTrACS, official boundary, fine layer)
    record       the WP11 deliverables (written later; absent on first run)

The output feeds `_wp11_canon.py --baseline`, which refuses to compute a number
whose source file has changed since the freeze.  Everything here is read-only;
the only writes are docs/_wp11_基线.json and one timestamped copy under
output_archive/.

USAGE
-----
  env\\run.ps1 tools\\_wp11_freeze.py              # write + archive
  env\\run.ps1 tools\\_wp11_freeze.py --dry-run    # print only
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

NEWROOT = Path(__file__).resolve().parent.parent
DOCS = NEWROOT / "docs"
ARCHIVE = NEWROOT / "output_archive"
OUT_JSON = DOCS / "_wp11_基线.json"

EXPECT_MANUSCRIPT = {
    r"manuscript\PAPER_MANUSCRIPT_FINAL.docx": (
        28933946,
        "39240D38FCF71ADB72BEA285249AFE5757E0327F26253D48BE45FA899C772F14"),
    r"manuscript\PAPER_MANUSCRIPT_v10.docx": (
        28193015,
        "40E306B03E2E54913CACF37CF62007226487BC3F879CE5ECADC186075BD1AD91"),
    r"manuscript\PAPER_MANUSCRIPT_v11.docx": (
        28193070,
        "7417FDE618D6C5114628B28C76C7E676141415EFA7BF50016BB13C2D472523CC"),
}

# role -> relative paths
TARGETS = {
    "manuscript": [
        r"manuscript\PAPER_MANUSCRIPT_FINAL.docx",
        r"manuscript\PAPER_MANUSCRIPT_v10.docx",
        r"manuscript\PAPER_MANUSCRIPT_v11.docx",
        r"manuscript\PAPER_MANUSCRIPT_v10.pdf",
        r"manuscript\PAPER_MANUSCRIPT_v11.pdf",
        r"manuscript\Cover_Letter_npjNaturalHazards_v2.docx",
    ],
    "output": [
        r"Climate\output\results\defense_sensitivity\defense_profile_eal.csv",
        r"Climate\output\results\risk_panel_high_confidence.csv",
        r"Climate\output\results\risk_panel_all_scenarios_high_confidence.csv",
        r"Climate\output\results\shanghai_city_cri_projection.csv",
        r"Climate\output\results\shanghai_city_monthly_climate_hazard.csv",
        r"Climate\output\results\tc_date_alignment_audit.csv",
        r"Climate\output\intermediate\svi_by_district.csv",
        r"Climate\output\intermediate\delta_isr_by_district.csv",
        r"Climate\output\intermediate\isr_panel.csv",
        r"Climate\output\intermediate\alpha_temp_series.csv",
        r"Climate\output\intermediate\sla_monthly.csv",
        r"Climate\output\intermediate\surge_heights_hist.csv",
        r"Finance\output\results\shanghai_finance_risk_index.csv",
        r"Finance\output\results\shanghai_fri_projection.csv",
        r"Finance\output\results\shanghai_climate_cvar_monthly.csv",
        r"Composite\output\results\shanghai_cfci_historical.csv",
        r"Composite\output\results\shanghai_cfci_projection.csv",
        r"_sensitivity_results\sensitivity_latest.csv",
        r"config\sensitivity_sweep.json",
        r"Composite\output\figures\cf_01_composite_index.png",
        r"Composite\output\figures\cf_02_triple_comparison.png",
        r"Composite\output\figures\cf_03_decomposition.png",
    ],
    "config": [
        r"Climate\00_config.py",
        r"Finance\00_config.py",
        r"Composite\00_config.py",
        r"Climate\01_hazard_tc.py",
        r"Climate\03_exposure.py",
        r"Climate\04_vulnerability.py",
        r"Climate\05_risk.py",
        r"Climate\06_defense_sensitivity.py",
        r"Climate\07_climate_index.py",
        r"Climate\generate_figures_new.py",
        r"Finance\generate_figures.py",
        r"Composite\generate_figures.py",
        r"Composite\01_composite_index.py",
        r"Finance\01_finance_risk_index.py",
        r"Finance\02_fri_projection.py",
        r"Finance\01a_climate_cvar.py",
        r"tools\gen_sensitivity_figures.py",
        r"tools\wp6_table8_recompute.py",
    ],
    "input": [
        r"data\Hazard_data\WP台风数据\IBTrACS.WP.v04r01.nc",
        r"data\Hazard_data\WP台风数据\IBTrACS.WP.v04r01_old_202510.nc",
        r"data\我国乡镇（街道）行政区划数据\_官方_天地图GS2024-0650\上海_区级_GS2024-0650.shp",
        r"data\我国乡镇（街道）行政区划数据\_官方_天地图GS2024-0650\上海_区级_GS2024-0650.dbf",
        r"data\我国乡镇（街道）行政区划数据\_官方_天地图GS2024-0650\上海_区级_GS2024-0650.prj",
        r"Climate\output\intermediate\building_elevation.npy",
        r"Climate\output\intermediate\building_coast_distance_m.npy",
        r"output_archive\baseline_legacy_20261016_212711"
        r"\Climate\output\results\defense_sensitivity\defense_profile_eal.csv",
    ],
    "runlog": [
        r"_v8_logs\run_20261016_230820.jsonl",
        r"_v8_logs\run_20261017_212732.jsonl",
        r"output_archive\boundary_official_A_20261016_230820\MANIFEST.json",
        r"output_archive\boundary_official_A_20261016_230820\_ARCHIVE_META.json",
    ],
}


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def stamp(p: Path) -> dict:
    return {
        "bytes": p.stat().st_size,
        "mtime": datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds"),
        "sha256": sha256(p),
    }


def collect() -> dict:
    out: dict = {
        "generated": datetime.now().isoformat(timespec="seconds"),
        "newroot": str(NEWROOT),
        "roles": {},
        "expected_manuscript": {},
    }
    for role, rels in TARGETS.items():
        block = {}
        for rel in rels:
            p = NEWROOT / rel
            block[rel] = stamp(p) if p.is_file() else {"missing": True}
        out["roles"][role] = block

    figs = sorted((NEWROOT / "manuscript" / "figures").glob("*.png"))
    out["roles"]["figure"] = {
        r"manuscript\figures\%s" % f.name: stamp(f) for f in figs
    }

    for rel, (want_b, want_sha) in EXPECT_MANUSCRIPT.items():
        p = NEWROOT / rel
        got = stamp(p) if p.is_file() else {"missing": True}
        out["expected_manuscript"][rel] = {
            "want_bytes": want_b,
            "want_sha256": want_sha,
            "got_bytes": got.get("bytes"),
            "got_sha256": got.get("sha256"),
            "ok": got.get("bytes") == want_b and got.get("sha256") == want_sha,
        }
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="WP11.0 freeze baseline")
    ap.add_argument("--out", default=str(OUT_JSON))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    data = collect()
    n_files = sum(len(v) for v in data["roles"].values())
    n_missing = [
        rel for role in data["roles"].values() for rel, v in role.items()
        if v.get("missing")]
    ok_ms = all(v["ok"] for v in data["expected_manuscript"].values())

    print("=== WP11.0 baseline freeze ===")
    for role in sorted(data["roles"]):
        print("  %-12s %3d files" % (role, len(data["roles"][role])))
    print("  total        %3d files" % n_files)
    for rel, v in data["expected_manuscript"].items():
        print("  [%s] %-46s %d B  %s" % (
            "OK" if v["ok"] else "MISMATCH", Path(rel).name,
            v["got_bytes"] or -1, (v["got_sha256"] or "-")[:16]))
    if n_missing:
        print("  MISSING (%d):" % len(n_missing))
        for rel in n_missing:
            print("    -", rel)

    stamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    arch = ARCHIVE / "_wp11_align_baseline"
    data["archive"] = str(arch)

    if args.dry_run:
        print("\n[dry-run] would write %s" % args.out)
        print("RESULT: DRY-RUN")
        return 0 if ok_ms and not n_missing else 1

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8", newline="\n")
    tmp.replace(out)

    arch.mkdir(parents=True, exist_ok=True)
    shutil.copy2(out, arch / out.name)
    print("\n  wrote %s (%.1f KB)" % (out.relative_to(NEWROOT),
                                       out.stat().st_size / 1024))
    print("  archive %s" % arch.relative_to(NEWROOT))

    if not ok_ms:
        print("RESULT: BASELINE-MISMATCH (a frozen docx changed)")
        return 2
    if n_missing:
        print("RESULT: BASELINE-INCOMPLETE (%d missing files)" % len(n_missing))
        return 1
    print("RESULT: BASELINE-FROZEN")
    return 0


if __name__ == "__main__":
    sys.exit(main())
