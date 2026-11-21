"""配置扫描器测试 — 生成/反向校验/模板校验（change simplify-configuration）。"""
from __future__ import annotations

from engram.backend.app.cli import config_scanner as cs


def test_scan_finds_literal_and_provider_reads():
    vars_ = cs.scan(cs.project_root())
    # 字面量读取
    assert "ENGRAM_MCP_ENABLED" in vars_
    assert "ENGRAM_MEMORY_USE" in vars_
    assert "TAVILY_API_KEY" in vars_
    assert vars_["ENGRAM_MCP_ENABLED"].default_text() == "false"
    # provider profile 动态读取的补齐
    assert "DEEPSEEK_API_KEY" in vars_
    assert "DEEPSEEK_BASE_URL" in vars_
    assert "DEEPSEEK_ENABLED" in vars_
    # 变量都能追到至少一个读取模块
    assert all(v.modules for v in vars_.values())


def test_scan_resolves_helper_calls_and_env_constants():
    """辅助函数参数 / 常量表里的变量也要进文档（否则参考不完整）。"""
    vars_ = cs.scan(cs.project_root())
    # _env_bool("ENGRAM_MULTIAGENT_ENABLED", True)
    assert vars_["ENGRAM_MULTIAGENT_ENABLED"].default_text() == "True"
    # os.environ.get(_WEB_UI_ENV, "") —— _WEB_UI_ENV 模块常量
    assert "ENGRAM_WEB_UI_ENABLED" in vars_
    # _ENV_KEYS = ("ENGRAM_CHECKPOINT_DSN", "ENGRAM_PG_DSN")
    assert "ENGRAM_PG_DSN" in vars_


def test_generated_docs_and_template_are_in_sync():
    problems = cs.validate(cs.project_root())
    assert problems == [], "\n".join(problems)


def test_fake_variable_in_docs_fails_validation():
    root = cs.project_root()
    docs = (root / cs._DOC_REL).read_text(encoding="utf-8")
    fake = docs + "\n| `ENGRAM_FAKE_VAR` | x | `fake.py` | fake |\n"
    problems = cs.validate(root, docs_text=fake)
    assert any("ENGRAM_FAKE_VAR" in p for p in problems)


def test_deleting_tavily_from_template_fails_validation():
    root = cs.project_root()
    template = (root / cs._TEMPLATE_REL).read_text(encoding="utf-8")
    without = "\n".join(
        line for line in template.splitlines() if "TAVILY_API_KEY" not in line
    )
    problems = cs.validate(root, template_text=without)
    assert any("TAVILY_API_KEY" in p for p in problems)


def test_env_example_is_minimal():
    """1.1：模板只保留密钥与权力授予开关，不含基础设施 DSN/调参旋钮。"""
    root = cs.project_root()
    keys = cs._template_keys((root / cs._TEMPLATE_REL).read_text(encoding="utf-8"))
    assert keys == {
        "DEEPSEEK_API_KEY",
        "OPENAI_API_KEY",
        "TAVILY_API_KEY",
        "ENGRAM_MCP_ENABLED",
        "ENGRAM_SANDBOX_USE",
    }
    assert not any("DSN" in key or "REDIS_URL" in key for key in keys)


def test_render_is_deterministic():
    first = cs.render(cs.scan(cs.project_root()))
    second = cs.render(cs.scan(cs.project_root()))
    assert first == second