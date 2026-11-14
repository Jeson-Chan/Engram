"""traces.md -> cold tier migration (issue 07, expand-contract 收尾).

MarkdownFileStore 的存量 MemoryTrace 一次性导入 Postgres 冷层。
迁移完成后 Markdown 存储退出运行路径（新写路径已立，旧文件仅作迁移来源）。

用法（命令行，仓库根）：
    python -m engram.backend.agents.memory.adapters.migration \
        --dsn postgresql://engram:engram@localhost:5432/engram \
        [--traces .engram/memory/traces.md] [--dry-run]

幂等：已存在的 trace_id 跳过（--dry-run 只报数量不写库）。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from engram.backend.agents.memory.adapters.pg_store import PostgresMemoryStore
from engram.backend.agents.memory.exceptions import MemoryConflictError


def load_markdown_traces(storage_path: str) -> list:
    """用 MarkdownFileStore 的既有解析路径读全部存量 trace（只读，不落盘）。"""
    from engram.backend.agents.memory.strategies.default.store import MarkdownFileStore

    store = MarkdownFileStore(storage_path)  # 构造即解析 traces.md 建索引
    return store.list_all()


def migrate_markdown_to_pg(
    storage_path: str,
    dsn: str,
    *,
    dry_run: bool = False,
) -> tuple[int, int]:
    """迁移 traces.md 存量到冷层。返回 (migrated, skipped)。

    幂等：trace_id 已在冷层 → 跳过计数（重跑不重复导入）。
    """
    traces = load_markdown_traces(storage_path)
    migrated = 0
    skipped = 0
    if dry_run:
        return 0, len(traces)
    cold = PostgresMemoryStore(dsn)
    try:
        for trace in traces:
            try:
                cold.add(trace)
                migrated += 1
            except MemoryConflictError:
                skipped += 1
    finally:
        cold.close()
    return migrated, skipped


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Migrate traces.md into the PG cold tier")
    parser.add_argument("--dsn", required=True, help="Postgres DSN of the cold tier")
    parser.add_argument("--traces", default=".engram/memory", help="Markdown storage root")
    parser.add_argument("--dry-run", action="store_true", help="count only, write nothing")
    args = parser.parse_args(argv)

    migrated, skipped = migrate_markdown_to_pg(args.traces, args.dsn, dry_run=args.dry_run)
    if args.dry_run:
        print(f"[migration] dry-run: {skipped} traces would migrate from {args.traces}")
        return 0
    print(f"[migration] migrated {migrated}, skipped (already present) {skipped}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
