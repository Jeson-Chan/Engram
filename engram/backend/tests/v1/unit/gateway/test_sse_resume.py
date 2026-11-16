"""SSE 断线重连测试 — Last-Event-ID 补齐，事件序列无缺失（issue 10）。

场景：客户端中途掐断（已收 N 条）→ 重连带 Last-Event-ID: N →
服务端补发缓冲里 N+1..M 的缺口事件 → 接续新流。与 Redis Stream
消费者组的续传语义同构（偏移量 + 缺口重放）。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, AsyncIterator

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessageChunk

from engram.backend.app.gateway.main import create_app
from engram.backend.app.gateway.sse_buffer import SSEEventBuffer


def _make_seeded_graph(seed: int, follow: int):
    """实例级计数：每个 graph 自己数轮次（首次 seed 条，之后 follow 条）。"""
    state = {'rounds': 0}

    class _Graph:
        async def astream(self, s, config=None, stream_mode=None):
            state['rounds'] += 1
            if state['rounds'] == 1:
                for i in range(seed):
                    yield ("messages", (AIMessageChunk(content="ev-%d" % i), {}))
            else:
                for i in range(follow):
                    yield ("messages", (AIMessageChunk(content="follow-%d" % i), {}))
            yield ("values", {"messages": []})

    return _Graph()


def _runtime_with_graph(graph) -> Any:
    class _RM:
        def create_run(self, thread_id, user_id=None, model_name=None, **kw):
            return SimpleNamespace(
                run_id="run-r", thread_id=thread_id, user_id=user_id,
                journal=SimpleNamespace(),
                output_dir="unused",
                config=SimpleNamespace(
                    runtime=SimpleNamespace(
                        expert_mode=False, plan_enabled=True, timezone="UTC",
                        max_loop_steps=4, graph_node_multiplier=3)),
            )

        def mark_running(self, r): pass

        def mark_success(self, r, usage=None): pass

        def mark_failed(self, r, e): pass

        def get_run(self, r): return None

    class _Runtime:
        run_manager = _RM()
        researcher_model_name = "fake"
        leader_agent = SimpleNamespace(graph=graph)

    return _Runtime()


def _client(runtime) -> TestClient:
    return TestClient(create_app(runtime_factory=lambda: runtime))


def _event_ids_and_contents(text: str):
    """解析 SSE 原文 → [(id, event_type, content)]。"""
    out = []
    for block in text.strip().split(chr(10) + chr(10)):
        if not block.strip():
            continue
        eid, etype, content = None, None, None
        for line in block.split(chr(10)):
            if line.startswith("id: "):
                eid = int(line[4:])
            elif line.startswith("event: "):
                etype = line[7:]
            elif line.startswith("data: "):
                import json

                data = json.loads(line[6:])
                content = data.get("content")
        out.append((eid, etype, content))
    return out


def test_resume_fills_gap_after_disconnect() -> None:
    """掐断在 ev-3（收到 4 条）→ 重连补齐 ev-4..ev-9 + 新流 follow-*。"""
    graph = _make_seeded_graph(10, 2)
    runtime = _runtime_with_graph(graph)
    client = _client(runtime)
    with client:
        sid = client.post("/sessions").json()["session_id"]
        first = client.post(f"/sessions/{sid}/chat", json={"message": "Q"})
        parsed = _event_ids_and_contents(first.text)
        contents = [c for _, t, c in parsed if t == "answer"]
        assert len(contents) == 10  # 全量收到（TestClient 不真断——首轮基线）
        last_id = max(i for i, _, _ in parsed if i is not None)
            # 模拟掐断：客户端只保留到 cut_id（id 连续含 done 帧）
        cut_id = last_id - 6  # 掐在 ev-4 左右
        # 重连：带 Last-Event-ID=cut_id（TestClient 直接再发请求 + 头）
        second = client.post(
            f"/sessions/{sid}/chat",
            json={"message": "Q"},
            headers={"Last-Event-ID": str(cut_id)},
        )
    resumed = _event_ids_and_contents(second.text)
    pairs = [(i, t) for i, t, _ in resumed if i is not None]
    answer_ids = [i for i, t in pairs if t == "answer"]
    # 补发的 id 严格大于 cut_id（缺口从 cut_id 之后开始）
    assert answer_ids and all(i > cut_id for i in answer_ids)
    # 无缺失：掐断点后旧流的剩余 answer（6..10）+ 新流 answer（12,13）都在，
    # 中间的 11 是第一轮的 done 帧（重放必然带上——语义正确，非缺失）
    assert answer_ids[: 10 - cut_id] == list(range(cut_id + 1, 11))  # 缺口部分连续
    assert answer_ids[10 - cut_id:] == [12, 13]  # 新流接续（跳过重放的旧 done=11）
    # done 收尾（补的旧 done + 新 done 都可，至少一个）
    assert any(t == "done" for _, t in pairs)
    # done 收尾
    assert any(t == "done" for _, t in pairs)


def test_resume_without_header_is_fresh_stream() -> None:
    """无 Last-Event-ID 头 = 全新订阅（不补发，正常流）。"""
    graph = _make_seeded_graph(3, 1)
    runtime = _runtime_with_graph(graph)
    client = _client(runtime)
    with client:
        sid = client.post("/sessions").json()["session_id"]
        resp = client.post(f"/sessions/{sid}/chat", json={"message": "Q"})
    parsed = _event_ids_and_contents(resp.text)
    types = [t for _, t, _ in parsed]
    assert types.count("answer") == 3
    assert types[-1] == "done"


def test_buffer_semantics_gap_beyond_capacity() -> None:
    """缓冲容量截断：缺口超出容量 → replay_after 返空（dropped 场景）。"""
    buf = SSEEventBuffer(capacity=3)
    for i in range(5):
        buf.append("event-%d" % i)
    # 容量 3：缓冲只存 id 3,4,5；从 id 1 重连 → 缺口无法补（1 < 3-1）
    assert buf.replay_after(1) == []
    assert buf.dropped is True
    # 从 id 3 重连：补 4,5
    got = buf.replay_after(3)
    assert [eid for eid, _ in got] == [4, 5]
    # 从 id 0（全新订阅，无历史）——从头给全量（0 不算缺口）
    got2 = buf.replay_after(0)
    assert [eid for eid, _ in got2] == [3, 4, 5]


def test_frames_carry_id_header() -> None:
    """每帧带 id: 行（SSE 规范——客户端重连时自动上报依据）。"""
    graph = _make_seeded_graph(2, 1)
    runtime = _runtime_with_graph(graph)
    client = _client(runtime)
    with client:
        sid = client.post("/sessions").json()["session_id"]
        resp = client.post(f"/sessions/{sid}/chat", json={"message": "Q"})
    parsed = _event_ids_and_contents(resp.text)
    ids = [i for i, _, _ in parsed if i is not None]
    assert ids == sorted(ids)  # 单调递增
    assert len(ids) >= 3       # 2 answer + done 每帧都有
