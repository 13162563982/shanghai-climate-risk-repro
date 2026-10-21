"""在 PAPER_MANUSCRIPT_v11.docx 上复跑 G7 闸门（不修改已验证的 _gate_g7.py）。

原理：G7 的全部断言都基于「文字/表格/公式/图片」内容，而 v11 只是给 37 个
图注短标签段落加了 ``<w:keepNext/>``（纯排版属性，不产生任何文本），
因此 G7 必须仍然 14/14 PASS。本包装器只把 G7 里的 ``V10`` 全局变量重绑到
v11 路径，其它逻辑、阈值、期望值一律不动。

Run:
    & ".\\env\\run.ps1" tools\\_gate_g7_v11.py
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

NEWROOT = Path(__file__).resolve().parent.parent


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def main() -> int:
    g7 = load(NEWROOT / "tools" / "_gate_g7.py", "gate_g7")
    target = NEWROOT / "manuscript" / "PAPER_MANUSCRIPT_v11.docx"
    if not target.is_file():
        print("ERROR: 缺少 %s" % target)
        return 2
    g7.V10 = target  # 只改这一个全局变量
    rc = g7.main()
    print("\n[wrapper] 复跑对象：%s（SHA %s…）"
          % (target.name, __import__("hashlib").sha256(target.read_bytes()).hexdigest()[:16].upper()))
    return rc


if __name__ == "__main__":
    sys.exit(main())
