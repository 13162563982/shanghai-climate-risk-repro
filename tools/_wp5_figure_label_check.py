"""WP5.6 helper: collect the 41 figures and crop label regions for inspection.

Writes:
  * manuscript\\figures\\             - all 41 final figures (plan section 3)
  * _finalcheck\\labelcheck\\*.png    - title / footnote strips of the 6 renamed figures

The crops are what a human (or an OCR pass) needs to confirm that FRI/CFCI are
gone and HSI/CCHI are present.
"""

import shutil
import sys
from pathlib import Path

from PIL import Image

NEWROOT = Path(__file__).resolve().parent.parent

SOURCES = [
    (r"Climate\output\figures_new", "**/*.png"),
    (r"Finance\output\figures", "*.png"),
    (r"Composite\output\figures", "*.png"),
]
SENS = NEWROOT / "manuscript" / "figures"

RENAMED = {
    "fi_01_finance_risk_index.png": "Finance",
    "fi_02_sub_indicator_decomposition.png": "Finance",
    "fi_04_fri_vs_cri_overlay.png": "Finance",
    "cf_01_composite_index.png": "Composite",
    "cf_02_triple_comparison.png": "Composite",
    "cf_03_decomposition.png": "Composite",
}
# crop bands as fractions of image height (title on top, footnote at bottom)
BANDS = {"title": (0.0, 0.13), "footnote": (0.86, 1.0)}


def main() -> int:
    out_dir = NEWROOT / "manuscript" / "figures"
    out_dir.mkdir(parents=True, exist_ok=True)

    found = {}
    for rel, pat in SOURCES:
        base = NEWROOT / rel
        if not base.exists():
            continue
        for p in base.glob(pat):
            dst = out_dir / p.name
            shutil.copy2(p, dst)
            found[p.name] = p
    n = len(found)
    print(f"collected {n} figures -> {out_dir}")

    crops_dir = NEWROOT / "_finalcheck" / "labelcheck"
    crops_dir.mkdir(parents=True, exist_ok=True)
    made = 0
    for name, src in RENAMED.items():
        p = found.get(name)
        if p is None:
            print(f"  [WARN] not generated: {name}")
            continue
        im = Image.open(p).convert("RGB")
        w, h = im.size
        for band, (a, b) in BANDS.items():
            im.crop((0, int(h * a), w, int(h * b))).save(
                crops_dir / f"{name.replace('.png', '')}__{band}.png")
            made += 1
        print(f"  {name}: {w}x{h}")
    print(f"wrote {made} label crops -> {crops_dir}")
    return 0 if n >= 37 else 1


if __name__ == "__main__":
    sys.exit(main())
