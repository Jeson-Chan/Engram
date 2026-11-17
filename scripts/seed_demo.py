"""演示 seed 薄入口 — python scripts/seed_demo.py [--clean]。

等价于 python -m engram.backend.app.demo.seed（见该模块 docstring）。
"""
from __future__ import annotations

import runpy
import sys
from pathlib import Path

# 脚本启动时 sys.path[0] 是本目录——补项目根，保证 import engram 走仓库源码
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# 从项目根加载 .env（与网关/CLI 同款行为）
try:
    from dotenv import load_dotenv

    load_dotenv(_PROJECT_ROOT / ".env")
except ImportError:
    pass

runpy.run_module(
    "engram.backend.app.demo.seed", run_name="__main__", alter_sys=True,
)
