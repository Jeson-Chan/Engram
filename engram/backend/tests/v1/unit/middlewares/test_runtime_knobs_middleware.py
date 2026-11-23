"""RuntimeKnobsMiddleware 单测（runtime-knobs）— request.model 替换与否。"""

from __future__ import annotations

from types import SimpleNamespace

from engram.backend.agents.middlewares.runtime_knobs_middleware import (
    RuntimeKnobsMiddleware,
)


class _BindableModel:
    """最小可 bind 模型桩：记录 bind kwargs。"""

    def __init__(self, cls_name: str = "ChatOpenAI") -> None:
        self._cls_name = cls_name
        self.bound: list[dict] = []

    def bind(self, **kwargs):
        self.bound.append(kwargs)
        return _BoundMarker(kwargs)

    # type(model).__name__ 用于 kind 推断——用实例属性不行，改用子类
    def __class_getitem__(cls, _item):  # pragma: no cover
        return cls


class ChatOpenAI(_BindableModel):
    pass


class ChatDeepSeek(_BindableModel):
    pass


class _BoundMarker:
    def __init__(self, kwargs: dict) -> None:
        self.kwargs = kwargs


class _Request:
    """duck-type ModelRequest：middleware 只读 runtime/model、调 override。"""

    def __init__(self, model, context: dict | None = None) -> None:
        self.model = model
        self.runtime = SimpleNamespace(context=context or {}) if context is not None else None
        self.replaced = False

    def override(self, **kwargs):
        self.replaced = True
        return _Request(kwargs.get("model", self.model), getattr(self.runtime, "context", None) if self.runtime else None)


def _mw() -> RuntimeKnobsMiddleware:
    return RuntimeKnobsMiddleware()


def test_effort_binds_model() -> None:
    model = ChatOpenAI()
    req = _Request(model, {"reasoning_effort": "low"})
    out = _mw()._override_if_needed(req)
    assert isinstance(out.model, _BoundMarker)
    assert out.model.kwargs == {"reasoning_effort": "low"}
    assert req.replaced is True


def test_off_or_missing_unchanged() -> None:
    model = ChatOpenAI()
    for ctx in ({}, {"reasoning_effort": None}, {"reasoning_effort": "off"}):
        req = _Request(model, ctx)
        out = _mw()._override_if_needed(req)
        assert out.model is model
    assert model.bound == []


def test_unsupported_provider_unchanged() -> None:
    model = ChatDeepSeek()
    req = _Request(model, {"reasoning_effort": "high"})
    out = _mw()._override_if_needed(req)
    assert out.model is model
    assert model.bound == []


def test_runtime_none_unchanged() -> None:
    model = ChatOpenAI()
    req = _Request(model, None)
    out = _mw()._override_if_needed(req)
    assert out.model is model