"""事件语义契约测试 — 解析 docs/event-semantics.md 的机器可读示例。

后端侧引用（任务 1.3）：文档中的 `sse` 示例块必须能被服务端帧格式
（id/event/data + JSON 公共字段）逐帧解析。前端 Vitest（任务 5.2）
对同一文档做同构解析——两侧共用同一份事实。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

_DOC = Path(__file__).parents[6] / "docs" / "event-semantics.md"

_SSE_BLOCK_RE = re.compile(r"```sse\n(.*?)```", re.DOTALL)

# 公共字段：每种事件类型的 data JSON 都必须携带（值可为 null）
_COMMON_FIELDS = ("type", "content", "tool_name", "tool_args", "tool_result", "msg_id")

# 各类型的关键非空字段（契约表 §2）
_REQUIRED_NON_NULL = {
    "answer": ("content",),
    "thinking": ("content",),
    "tool_start": ("tool_name",),
    "tool_end": ("tool_name", "tool_result"),
    "skill_active": ("content",),
    "budget_update": ("budget",),
    "done": (),
    "error": ("content",),
}


def _extract_blocks() -> list[str]:
    """提取文档全部 ```sse 示例块。"""
    text = _DOC.read_text(encoding="utf-8")
    blocks = _SSE_BLOCK_RE.findall(text)
    assert blocks, f"{_DOC} 未找到 sse 示例块"
    return blocks


def _parse_frames(block: str) -> list[tuple[str, dict]]:
    """按服务端帧格式解析一个示例块 → [(id, event, data)]。"""
    frames = []
    for raw_frame in block.split("\n\n"):
        if not raw_frame.strip():
            continue
        event_id: str | None = None
        event_type: str | None = None
        data_line: str | None = None
        for line in raw_frame.splitlines():
            line = line.rstrip("\r")
            if line.startswith("id: "):
                event_id = line[4:].strip()
            elif line.startswith("event: "):
                event_type = line[7:].strip()
            elif line.startswith("data: "):
                data_line = line[6:]
        assert event_id is not None, f"帧缺 id 行: {raw_frame!r}"
        assert event_type is not None, f"帧缺 event 行: {raw_frame!r}"
        assert data_line is not None, f"帧缺 data 行: {raw_frame!r}"
        frames.append((event_id, event_type, json.loads(data_line)))
    return frames


def test_doc_blocks_parse_as_valid_sse():
    """每个示例块都解析为非空帧序列，id 严格递增从 1 起。"""
    for block in _extract_blocks():
        frames = _parse_frames(block)
        assert frames
        ids = [int(fid) for fid, _, _ in frames]
        assert ids == list(range(1, len(ids) + 1)), f"id 必须从 1 连续递增: {ids}"


def test_common_fields_always_present():
    """每帧 data 都携带全部公共字段（可为 null，不省略）。"""
    for block in _extract_blocks():
        for _, _, data in _parse_frames(block):
            for field in _COMMON_FIELDS:
                assert field in data, f"缺公共字段 {field}: {data}"


def test_event_type_matches_event_line():
    """event: 行与 data.type 一致。"""
    for block in _extract_blocks():
        for _, event_type, data in _parse_frames(block):
            assert data["type"] == event_type


def test_required_non_null_fields_per_type():
    """各类型的关键字段非 null（契约表 §2）。"""
    for block in _extract_blocks():
        for _, event_type, data in _parse_frames(block):
            for field in _REQUIRED_NON_NULL.get(event_type, ()):
                assert data.get(field) is not None, f"{event_type} 的 {field} 不应为 null"


def test_stream_terminates_with_done():
    """每个示例流以 done 收尾（客户端终态判定契约）。"""
    for block in _extract_blocks():
        frames = _parse_frames(block)
        assert frames[-1][1] == "done", "流最后一帧必须是 done"


def test_budget_update_carries_budget_snapshot():
    """budget_update 必须带 budget 快照（total/fraction/window）。"""
    found = False
    for block in _extract_blocks():
        for _, _, data in _parse_frames(block):
            if data["type"] == "budget_update":
                found = True
                budget = data["budget"]
                assert {"total", "fraction", "window"} <= set(budget)
    assert found, "示例块必须覆盖 budget_update 事件"


def test_gap_error_semantics_documented():
    """缺口超限错误语义在文档中有定义（§3）。"""
    text = _DOC.read_text(encoding="utf-8")
    assert "resume gap exceeded buffer capacity" in text
    assert "X-Engram-Events-Dropped" in text
    assert "Last-Event-ID" in text
