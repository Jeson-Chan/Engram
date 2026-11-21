"""Web 静态产物挂载 + history fallback — /app（feature flag）。

gateway-client-api / 兼容与错误语义（design.md 决策 1 + 迁移计划 3）：
- `ENGRAM_WEB_UI_ENABLED=true` 且构建产物存在 → `/app` 返回 index.html，
  静态资源挂载，未知前端路由（`/app/...` 无对应文件）回退到 index
- 关闭（默认）或产物缺失 → 不挂载，网关行为完全不变（Web 故障不影响
  终端入口的红线）
- SPA 路由：`/app` 与 `/app/*` 均回退 index（前端 history 路由由 JS 接管）
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from starlette.staticfiles import StaticFiles

logger = logging.getLogger(__name__)

_WEB_UI_ENV = "ENGRAM_WEB_UI_ENABLED"
# 构建产物目录（仓库根锚定——main.py 同款 parents[4] 根计算）：
# web/dist = 宿主机构建产物（compose 挂载，存在时优先）；
# web/built = 镜像 multi-stage 构建产物（Dockerfile COPY，宿主机无产物时兜底）。
_DIST_CANDIDATES = ("web/dist", "web/built")


def web_dist_path(project_root: Path | None = None) -> Path | None:
    """构建产物路径：ENGRAM_WEB_UI_DIST 优先，否则按候选顺序查找。

    候选顺序 web/dist（宿主机）→ web/built（镜像内 multi-stage 产物）。
    project_root 仅测试注入；运行时锚定仓库根。
    """
    configured = os.environ.get("ENGRAM_WEB_UI_DIST", "").strip()
    if configured:
        path = Path(configured)
        return path if path.is_dir() else None
    root = project_root or Path(__file__).resolve().parents[4]
    for candidate in _DIST_CANDIDATES:
        path = root / candidate
        if path.is_dir():
            return path
    return None


def mount_web_ui(app: FastAPI) -> bool:
    """挂载 Web UI（flag 开且产物在）。返是否挂载。

    调用点：create_app 尾部。未挂载时零路由注册——行为不变红线。
    """
    enabled = os.environ.get(_WEB_UI_ENV, "").strip().lower() in ("1", "true", "yes")
    if not enabled:
        return False
    dist = web_dist_path()
    if dist is None or not (dist / "index.html").is_file():
        logger.warning(
            "%s=true but no web build found (web/dist or ENGRAM_WEB_UI_DIST); "
            "gateway runs without the web UI", _WEB_UI_ENV,
        )
        return False

    # 静态资源：/app/assets/... → dist/assets/...
    assets_dir = dist / "assets"
    if assets_dir.is_dir():
        app.mount("/app/assets", StaticFiles(directory=str(assets_dir)), name="web_assets")

    index_html = dist / "index.html"

    @app.get("/app", include_in_schema=False)
    def web_index():
        return FileResponse(str(index_html))

    @app.get("/app/{full_path:path}", include_in_schema=False)
    def web_fallback(full_path: str):
        """SPA history 路由回退：未知前端路由返回 index（JS 路由接管）。

        安全（review critical）：full_path 来自 URL——先 resolve 再校验
        落在 dist 根内（`..`/绝对路径/编码穿越一律拒绝），否则 dist 外的
        任意文件（.env 密钥、gateway.db）可被读取。资源路径已由上面的
        assets mount（StaticFiles，自带防穿越）接管；此处只兜前端路由。
        """
        dist_root = dist.resolve()
        candidate = (dist_root / full_path.lstrip("/")).resolve()
        if full_path and candidate.is_relative_to(dist_root) and candidate.is_file():
            return FileResponse(str(candidate))
        return FileResponse(str(index_html))

    logger.info("web UI mounted at /app (dist=%s)", dist)
    return True
