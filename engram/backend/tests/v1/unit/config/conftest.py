"""Provider env isolation for config tests.

Importing the CLI (or the gateway) loads the real project-root .env at
module level, which leaks the user's provider settings (e.g.
OPENAI_MODEL) into the process env and makes provider-config tests
machine-dependent. Pin the provider-relevant vars to deterministic
values at collection time, before any test module import runs.
"""
from __future__ import annotations

import os

_PIN = {
    "OPENAI_API_KEY": "test-key-openai",
    "OPENAI_MODEL": "",
    "OPENAI_BASE_URL": "",
    "DEEPSEEK_API_KEY": "test-key-deepseek",
    "DEEPSEEK_MODEL": "",
    "DEEPSEEK_BASE_URL": "",
    "QWEN_API_KEY": "",
    "ANTHROPIC_API_KEY": "",
    "GEMINI_API_KEY": "",
}

for _k, _v in _PIN.items():
    os.environ[_k] = _v
