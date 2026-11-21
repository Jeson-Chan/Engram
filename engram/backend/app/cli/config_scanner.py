"""配置扫描器 — 静态检索代码中的环境变量读取点，生成配置参考文档。

设计（openspec change simplify-configuration, D4）：
- 只读：AST 扫描源码，不 import 运行时模块，不改任何配置读取路径。
- `docs/configuration.md` 由本脚本生成，禁止手工编辑。
- `--check` 做三件事（CI 用）：
  1. 重新生成的内容与磁盘文档一致（漂移即失败）；
  2. 文档中的每个变量都能在代码中找到读取点（反向校验）；
  3. `.env.example` 的变量 ⊆ 代码变量，且必需的密钥/授权开关都在模板中。

运行：
    python -m engram.backend.app.cli.config_scanner
    python -m engram.backend.app.cli.config_scanner --check
"""
from __future__ import annotations

import argparse
import ast
import difflib
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

_DOC_REL = "docs/configuration.md"
_TEMPLATE_REL = ".env.example"
_SCAN_ROOT_REL = "engram/backend"
_EXCLUDE_DIRS = {"tests", "__pycache__"}
_SELF = "engram/backend/app/cli/config_scanner.py"

# 模板必须包含的密钥与权力授予开关（缺一即校验失败）。
REQUIRED_TEMPLATE_KEYS = frozenset({
    "DEEPSEEK_API_KEY",
    "TAVILY_API_KEY",
    "ENGRAM_MCP_ENABLED",
    "ENGRAM_SANDBOX_USE",
})

# 模板中允许出现但运行时读取点由 provider 动态拼接的变量名。
AUTHORIZATION_SWITCHES = frozenset({"ENGRAM_MCP_ENABLED", "ENGRAM_SANDBOX_USE"})

_ENV_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]+$")
_TEMPLATE_ACTIVE_RE = re.compile(r"^\s*([A-Z][A-Z0-9_]+)\s*=")
_TEMPLATE_COMMENTED_RE = re.compile(r"^\s*#\s*([A-Z][A-Z0-9_]+)\s*=")

# 环境变量读取辅助函数名（如 _env_bool / _env_int / read_env）。
_ENV_HELPER_RE = re.compile(r"(^|_)(env|environ)(_|$)", re.IGNORECASE)
_ENV_NAME_SUFFIXES = (
    "_API_KEY", "_KEY", "_DSN", "_URL", "_TOKEN", "_PATH",
    "_MODEL", "_ENABLED", "_HOME", "_DIR", "_SECRET",
)
_PROVIDER_KEY_PREFIXES = (
    "DEEPSEEK", "OPENAI", "QWEN", "ANTHROPIC", "GEMINI", "MOONSHOT",
    "OPENROUTER", "XAI_", "ZHIPU", "NVIDIA", "OLLAMA", "GROQ",
    "MISTRAL", "TOGETHER", "ZAI_", "PI_", "CLAUDE_CODE", "CODEX",
)

_PURPOSES: dict[str, str] = {
    "TAVILY_API_KEY": "Tavily 联网搜索密钥（留空回退 DuckDuckGo）",
    "ENGRAM_SANDBOX_USE": "沙箱 provider 路径（空=未授权/禁用）",
    "ENGRAM_SANDBOX_ALLOW_HOST_BASH": "Local 沙箱是否允许宿主机 bash",
    "ENGRAM_SANDBOX_IMAGE": "Docker 沙箱镜像",
    "ENGRAM_SANDBOX_PORT": "沙箱容器起始端口（占用时递增）",
    "ENGRAM_SANDBOX_EXECUTOR": "沙箱执行环境（local / wsl）",
    "ENGRAM_SANDBOX_WSL_DISTRO": "WSL 发行版名",
    "ENGRAM_SANDBOX_WSL_USER": "WSL 执行用户",
    "ENGRAM_SANDBOX_CONTAINER_PREFIX": "沙箱容器名前缀",
    "ENGRAM_SANDBOX_IDLE_TIMEOUT": "沙箱空闲销毁秒数（0=不销毁）",
    "ENGRAM_SANDBOX_REPLICAS": "沙箱预热池大小（0=不预热）",
    "ENGRAM_MCP_ENABLED": "MCP 总开关（权力授予，默认关闭）",
    "ENGRAM_MCP_CONFIG_PATH": "MCP server 配置文件路径",
    "ENGRAM_MEMORY_USE": "记忆主 Provider（空=禁用；default=Markdown+BM25）",
    "ENGRAM_MEMORY_STORAGE_PATH": "记忆 Markdown 持久化根目录",
    "ENGRAM_MEMORY_ENABLE_RECALL": "记忆召回开关（before_model）",
    "ENGRAM_MEMORY_ENABLE_EXTRACT": "实时抽取开关（after_model）",
    "ENGRAM_MEMORY_TOKEN_BUDGET": "召回注入 token 预算上限",
    "ENGRAM_MEMORY_PHASE2_ENABLED": "L5 自动沉淀（Phase 2）",
    "ENGRAM_MEMORY_PHASE2_TURNS": "自动沉淀触发轮数",
    "ENGRAM_MEMORY_TTL_SECONDS": "热层 TTL 覆盖（秒，测试/演示）",
    "ENGRAM_MEMORY_PG_DSN": "记忆冷层 Postgres DSN（compose 注入）",
    "ENGRAM_REDIS_URL": "记忆热层 Redis URL（compose 注入）",
    "ENGRAM_CHECKPOINT_DSN": "LangGraph 会话状态持久层 DSN（compose 注入）",
    "ENGRAM_PG_DSN": "网关 Postgres DSN",
    "ENGRAM_RUNS_PG_DSN": "Run 记录 Postgres DSN",
    "ENGRAM_GATEWAY_DB": "网关会话库路径（SQLite）",
    "ENGRAM_WEB_UI_ENABLED": "Web 工作台静态挂载开关",
    "ENGRAM_WEB_UI_DIST": "Web 构建产物目录",
    "ENGRAM_SKILL_ENABLED": "Skill 模块总开关",
    "ENGRAM_SKILL_DB_PATH": "Skill SQLite 路径",
    "ENGRAM_SKILL_DIRS": "Skill 扫描目录（逗号分隔）",
    "ENGRAM_SKILL_INCLUDE_BUILTIN": "是否加载 builtin skill",
    "ENGRAM_SKILL_MAX_INJECT": "单轮最多注入 skill 数",
    "ENGRAM_SKILL_QUALITY_THRESHOLD": "skill 质量淘汰阈值",
    "ENGRAM_SKILL_MIN_SELECTIONS": "淘汰判定最少命中数",
    "ENGRAM_MULTIAGENT_ENABLED": "MultiAgent 总开关",
    "ENGRAM_MULTIAGENT_SPECIALISTS": "启用的 specialist 列表",
    "ENGRAM_MULTIAGENT_AUTO_APPROVE": "specialist 调用自动批准",
    "ENGRAM_LOOP_DETECTION_ENABLED": "搜索循环保护总开关",
    "ENGRAM_SEARCH_SOFT_LIMIT": "搜索软上限（注入停止提醒）",
    "ENGRAM_SEARCH_HARD_LIMIT": "搜索硬上限（强制收尾）",
    "ENGRAM_LLM_REQUEST_TIMEOUT": "LLM 单请求超时（秒）",
    "ENGRAM_LLM_MAX_RETRIES": "LLM SDK 重试次数",
    "ENGRAM_INTERNAL_LLM_TIMEOUT": "内部辅助 LLM 调用超时（秒）",
}

_PREFIX_PURPOSES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"^ENGRAM_SANDBOX_"), "沙箱配置"),
    (re.compile(r"^ENGRAM_MCP_"), "MCP 配置"),
    (re.compile(r"^ENGRAM_MEMORY_"), "记忆配置"),
    (re.compile(r"^ENGRAM_SKILL_"), "Skill 配置"),
    (re.compile(r"^ENGRAM_MULTIAGENT_"), "MultiAgent 配置"),
    (re.compile(r"^ENGRAM_LOOP_|^ENGRAM_SEARCH_"), "搜索循环保护"),
    (re.compile(r"^ENGRAM_LLM_"), "LLM 超时/重试"),
    (re.compile(r"^ENGRAM_"), "Engram 运行时配置"),
    (re.compile(r"^CLAUDE_CODE_|^CODEX_|^ANTHROPIC_AUTH_TOKEN$"),
     "Claude/Codex specialist 凭证"),
    (re.compile(r"_API_KEY$"), "API 密钥"),
    (re.compile(r"_BASE_URL$"), "API 端点"),
    (re.compile(r"_MODEL$"), "模型名"),
    (re.compile(r"_ENABLED$"), "功能开关（false=禁用）"),
)


@dataclass(frozen=True)
class VarRead:
    """一次环境变量读取点。"""

    name: str
    default: str
    module: str
    purpose: str = ""


@dataclass
class ConfigVar:
    """聚合后的配置变量（同名读取点合并）。"""

    name: str
    defaults: set[str] = field(default_factory=set)
    modules: set[str] = field(default_factory=set)
    purpose: str = ""

    def default_text(self) -> str:
        if not self.defaults:
            return "—"
        # "—" 表示辅助函数未声明默认值；同名变量已有显式默认值时忽略它。
        meaningful = self.defaults - {"—"}
        ordered = sorted(meaningful or self.defaults)
        return " / ".join(ordered)


def project_root() -> Path:
    """本文件位于 engram/backend/app/cli/，parents[4] 即仓库根。"""
    return Path(__file__).resolve().parents[4]


def _display_default(raw: str) -> str:
    if raw == "":
        return "（空）"
    return raw


def _purpose_for(name: str) -> str:
    if name in _PURPOSES:
        return _PURPOSES[name]
    for pattern, purpose in _PREFIX_PURPOSES:
        if pattern.search(name):
            return purpose
    return "见读取模块"


def _looks_like_env_key(value: str) -> bool:
    """集合/常量里的字符串是否像环境变量名（避免把 "CMD" 之类收进文档）。"""
    if not _ENV_NAME_RE.match(value):
        return False
    if value.startswith("ENGRAM_") or value == "TAVILY_API_KEY":
        return True
    if value.endswith(_ENV_NAME_SUFFIXES):
        return True
    return value.startswith(_PROVIDER_KEY_PREFIXES)


def _module_env_constants(tree: ast.Module) -> dict[str, list[str]]:
    """模块级常量 → 环境变量名列表（如 _WEB_UI_ENV / _ENV_KEYS）。"""
    mapping: dict[str, list[str]] = {}
    for node in tree.body:
        value: ast.expr | None = None
        targets: list[ast.expr] = []
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign):
            targets, value = [node.target], node.value
        if value is None:
            continue
        names = _env_names_in_value(value)
        if not names:
            continue
        for target in targets:
            if isinstance(target, ast.Name):
                mapping[target.id] = names
    return mapping


def _env_names_in_value(value: ast.expr) -> list[str]:
    """字符串 / tuple / list / dict 中像环境变量名的字面量。"""
    if isinstance(value, ast.Constant) and isinstance(value.value, str):
        return [value.value] if _looks_like_env_key(value.value) else []
    if isinstance(value, (ast.Tuple, ast.List, ast.Set)):
        names: list[str] = []
        for element in value.elts:
            names.extend(_env_names_in_value(element))
        return names
    if isinstance(value, ast.Dict):
        names = []
        for key in value.keys:
            names.extend(_env_names_in_value(key) if key is not None else [])
        for item in value.values:
            names.extend(_env_names_in_value(item))
        return names
    return []


def _name_from_arg(arg: ast.expr, const_map: dict[str, list[str]]) -> str | None:
    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
        return arg.value
    if isinstance(arg, ast.Name):
        names = const_map.get(arg.id)
        if names and len(names) == 1:
            return names[0]
    return None


def _call_env_name(node: ast.Call, const_map: dict[str, list[str]]) -> str | None:
    """识别 os.environ.get("X") / os.getenv("X") 的变量名（含常量间接引用）。"""
    func = node.func
    is_environ_get = (
        isinstance(func, ast.Attribute)
        and func.attr == "get"
        and isinstance(func.value, ast.Attribute)
        and func.value.attr == "environ"
        and isinstance(func.value.value, ast.Name)
        and func.value.value.id == "os"
    )
    is_os_getenv = (
        isinstance(func, ast.Attribute)
        and func.attr == "getenv"
        and isinstance(func.value, ast.Name)
        and func.value.id == "os"
    )
    if not (is_environ_get or is_os_getenv):
        return None
    if not node.args:
        return None
    return _name_from_arg(node.args[0], const_map)


def _helper_env_name(node: ast.Call, const_map: dict[str, list[str]]) -> tuple[str, str] | None:
    """识别 `_env_bool("ENGRAM_X", default)` 这类辅助函数调用。"""
    func = node.func
    fname = func.attr if isinstance(func, ast.Attribute) else (
        func.id if isinstance(func, ast.Name) else ""
    )
    if not fname or not _ENV_HELPER_RE.search(fname):
        return None
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) and func.value.id == "os":
        return None  # 直接读取已在 _call_env_name 处理
    if not node.args:
        return None
    name = _name_from_arg(node.args[0], const_map)
    if name is None or not _looks_like_env_key(name):
        return None
    default = "—"
    if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
        default = _display_default(str(node.args[1].value))
    return name, default


def _call_default(node: ast.Call) -> str:
    if len(node.args) < 2:
        return "—"
    second = node.args[1]
    if isinstance(second, ast.Constant):
        return _display_default(str(second.value))
    return "（表达式）"


def _subscript_env_name(node: ast.Subscript, const_map: dict[str, list[str]]) -> str | None:
    value = node.value
    is_environ = (
        isinstance(value, ast.Attribute)
        and value.attr == "environ"
        and isinstance(value.value, ast.Name)
        and value.value.id == "os"
    )
    if not is_environ:
        return None
    return _name_from_arg(node.slice, const_map)


def _collection_env_names(tree: ast.Module) -> set[str]:
    """tuple/list/set/dict 字面量里的环境变量名（凭证列表 / env 映射表）。"""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
            for element in node.elts:
                if isinstance(element, ast.Constant) and isinstance(element.value, str):
                    if _looks_like_env_key(element.value):
                        names.add(element.value)
        elif isinstance(node, ast.Dict):
            for key in node.keys:
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    if _looks_like_env_key(key.value):
                        names.add(key.value)
            for item in node.values:
                if isinstance(item, ast.Constant) and isinstance(item.value, str):
                    if _looks_like_env_key(item.value):
                        names.add(item.value)
    return names


def _scan_source(path: Path, root: Path) -> list[VarRead]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return []
    rel = path.relative_to(root).as_posix()
    const_map = _module_env_constants(tree)
    reads: list[VarRead] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = _call_env_name(node, const_map)
            if name is not None:
                reads.append(VarRead(name=name, default=_call_default(node), module=rel))
                continue
            helper = _helper_env_name(node, const_map)
            if helper is not None:
                name, default = helper
                reads.append(VarRead(name=name, default=default, module=rel))
        elif isinstance(node, ast.Subscript):
            name = _subscript_env_name(node, const_map)
            if name is not None:
                reads.append(VarRead(name=name, default="—", module=rel))

    captured = {read.name for read in reads}
    for name in sorted(_collection_env_names(tree) - captured):
        reads.append(VarRead(name=name, default="—", module=rel))
    return reads


def _scan_provider_profiles(root: Path) -> list[VarRead]:
    """provider_*.py 通过 profile.env_key 动态读取，AST literal 扫描看不到。

    这里解析 PROVIDER_PROFILES 的声明字面量，补齐 provider 密钥/端点/模型，
    以及 provider_config.py 拼接的 `{NAME}_ENABLED`。
    """
    path = root / "engram/backend/agents/config/provider_profile.py"
    if not path.exists():
        return []
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return []
    rel = "engram/backend/agents/config/provider_profile.py"
    enabled_rel = "engram/backend/agents/config/provider_config.py"
    reads: list[VarRead] = []
    for node in tree.body:
        targets: list[ast.expr] = []
        value: ast.expr | None = None
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign):
            targets, value = [node.target], node.value
        if not targets or not isinstance(value, ast.List):
            continue
        if not any(isinstance(t, ast.Name) and t.id == "PROVIDER_PROFILES" for t in targets):
            continue
        for element in value.elts:
            if not isinstance(element, ast.Call):
                continue
            kwargs = {kw.arg: kw.value for kw in element.keywords if kw.arg}
            name = _const_str(kwargs.get("name"))
            if not name:
                continue
            env_key = _const_str(kwargs.get("env_key"))
            env_base_url = _const_str(kwargs.get("env_base_url"))
            env_model = _const_str(kwargs.get("env_model"))
            base_default = _const_str(kwargs.get("default_base_url"))
            model_default = _const_str(kwargs.get("default_model"))
            no_key = _const_bool(kwargs.get("no_key_required"))
            if env_key and not no_key:
                reads.append(VarRead(env_key, "—", rel, f"{name} API 密钥"))
            if env_base_url:
                reads.append(VarRead(
                    env_base_url, _display_default(base_default or ""), rel,
                    f"{name} API 端点",
                ))
            if env_model:
                reads.append(VarRead(
                    env_model, _display_default(model_default or ""), rel,
                    f"{name} 默认模型",
                ))
            reads.append(VarRead(
                f"{name.upper()}_ENABLED", "true", enabled_rel,
                f"单独禁用 {name}（false=禁用）",
            ))
    return reads


def _const_str(node: ast.expr | None) -> str:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return ""


def _const_bool(node: ast.expr | None) -> bool:
    if isinstance(node, ast.Constant) and isinstance(node.value, bool):
        return node.value
    return False


def scan(root: Path | None = None) -> dict[str, ConfigVar]:
    """扫描代码，返回 变量名 → ConfigVar。"""
    root = root or project_root()
    scan_root = root / _SCAN_ROOT_REL
    reads: list[VarRead] = []
    for path in sorted(scan_root.rglob("*.py")):
        if any(part in _EXCLUDE_DIRS for part in path.parts):
            continue
        rel = path.relative_to(root).as_posix()
        if rel == _SELF:
            continue
        reads.extend(_scan_source(path, root))
    reads.extend(_scan_provider_profiles(root))

    merged: dict[str, ConfigVar] = {}
    for read in reads:
        if not _ENV_NAME_RE.match(read.name):
            continue
        var = merged.setdefault(read.name, ConfigVar(name=read.name))
        var.defaults.add(read.default)
        var.modules.add(read.module)
        if read.purpose:
            var.purpose = read.purpose
    for var in merged.values():
        if not var.purpose:
            var.purpose = _purpose_for(var.name)
    return merged


def _escape_cell(text: str) -> str:
    return text.replace("|", "\\|")


def render(vars_: dict[str, ConfigVar]) -> str:
    lines = [
        "# Engram 配置参考",
        "",
        "> 本文件由扫描器自动生成，请勿手工编辑。",
        "> 生成：`python -m engram.backend.app.cli.config_scanner`",
        "> 校验（CI）：`python -m engram.backend.app.cli.config_scanner --check`",
        "",
        "下表列出代码实际读取的全部环境变量。`.env.example` 只保留密钥与权力授予开关；",
        "其余变量都有安全默认值，通常无需填写。Docker compose 路径下 DSN 与 Web 开关由",
        "`docker-compose.yml` 注入，用户 `.env` 中不需要出现。",
        "",
        "| 变量 | 默认值 | 读取模块 | 用途 |",
        "|------|--------|----------|------|",
    ]
    for name in sorted(vars_):
        var = vars_[name]
        modules = "<br>".join(f"`{m}`" for m in sorted(var.modules))
        lines.append(
            f"| `{_escape_cell(name)}` | {_escape_cell(var.default_text())} | "
            f"{modules} | {_escape_cell(var.purpose)} |"
        )
    lines.append("")
    return "\n".join(lines)


def _template_keys(text: str) -> set[str]:
    keys: set[str] = set()
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        active = _TEMPLATE_ACTIVE_RE.match(stripped)
        if active:
            keys.add(active.group(1))
            continue
        commented = _TEMPLATE_COMMENTED_RE.match(stripped)
        if commented:
            keys.add(commented.group(1))
    return keys


def _docs_vars(text: str) -> set[str]:
    """从生成的文档表格中提取反引号包裹的变量名。"""
    names: set[str] = set()
    for line in text.splitlines():
        if not line.startswith("| `"):
            continue
        first = line.split("|", 2)[1].strip()
        if first.startswith("`") and first.endswith("`"):
            names.add(first.strip("`"))
    return names


def validate(
    root: Path | None = None,
    *,
    docs_text: str | None = None,
    template_text: str | None = None,
) -> list[str]:
    """返回校验问题列表（空=通过）。"""
    root = root or project_root()
    vars_ = scan(root)
    code_names = set(vars_)
    problems: list[str] = []

    expected = render(vars_)
    docs_path = root / _DOC_REL
    actual = docs_text if docs_text is not None else (
        docs_path.read_text(encoding="utf-8") if docs_path.exists() else ""
    )
    if actual != expected:
        diff = list(difflib.unified_diff(
            actual.splitlines(), expected.splitlines(),
            fromfile=_DOC_REL, tofile=f"{_DOC_REL} (generated)", lineterm="",
        ))
        head = "\n".join(diff[:80])
        problems.append(
            f"{_DOC_REL} 与代码读取点不一致，请重新生成。\n{head}"
        )

    for name in sorted(_docs_vars(actual) - code_names):
        problems.append(f"文档中的变量 `{name}` 在代码中没有读取点")

    template_path = root / _TEMPLATE_REL
    template = template_text if template_text is not None else (
        template_path.read_text(encoding="utf-8") if template_path.exists() else ""
    )
    template_keys = _template_keys(template)
    for name in sorted(template_keys - code_names - AUTHORIZATION_SWITCHES):
        problems.append(f".env.example 中的变量 `{name}` 在代码中没有读取点")
    for name in sorted(REQUIRED_TEMPLATE_KEYS - template_keys):
        problems.append(f".env.example 缺少必需变量 `{name}`")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="config-scanner", description=__doc__)
    parser.add_argument("--check", action="store_true", help="校验文档/模板与代码一致（CI 用）")
    parser.add_argument("--root", default=None, help="仓库根（默认自动定位）")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve() if args.root else project_root()

    if args.check:
        problems = validate(root)
        if problems:
            for problem in problems:
                print(problem, file=sys.stderr)
            return 1
        print("configuration docs/template OK")
        return 0

    vars_ = scan(root)
    out = root / _DOC_REL
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(vars_), encoding="utf-8")
    print(f"wrote {_DOC_REL} ({len(vars_)} variables)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())