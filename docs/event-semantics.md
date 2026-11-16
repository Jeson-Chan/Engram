# SSE 事件语义（Web / TUI 共用契约）

本文档固化 `POST /sessions/{id}/chat` 与 `POST /sessions/{id}/research` 的 SSE 事件语义，是 Web 前端与 TUI 的**唯一权威来源**。前端 SSE 解析测试（`web/src/lib/__tests__/`）与后端流式测试（`engram/backend/tests/v1/unit/gateway/test_event_semantics.py`）都从本文的 `sse` 示例代码块提取样例帧做验证——修改事件语义时必须同步更新本文并保证两侧测试通过。

## 1. 传输与帧格式

- 端点：`POST /sessions/{session_id}/chat`、`POST /sessions/{session_id}/research`，请求体 JSON（`{"message": "..."}`）。
- 响应：`text/event-stream`，每帧形如：

```
id: 7
event: answer
data: {"type": "answer", "content": "...", "tool_name": null, "tool_args": null, "tool_result": null, "msg_id": "..."}

```

- `id:` 行是**每会话独立递增序号**（从 1 起）；`data` 是单行 JSON。
- 帧以**空行**结尾；`id:` 行在缓冲开启时存在（见 §3）。
- 心跳/空行由传输层处理，客户端解析器必须容忍 `\r\n` 与 `\n` 两种换行。

## 2. 事件类型

`data` JSON 的公共字段：`type`、`content`、`tool_name`、`tool_args`、`tool_result`、`msg_id`（可选 `budget`）。未用字段为 `null`，不省略。

| type | 语义 | 关键字段 | 出现于 |
|---|---|---|---|
| `thinking` | 推理 token 增量（deepseek reasoning delta） | `content` | chat/research |
| `answer` | 回答 token 增量，界面按 delta 追加渲染 | `content`、`msg_id` | chat/research |
| `tool_start` | 工具调用开始 | `tool_name`、`tool_args` | chat/research |
| `tool_end` | 工具调用结束（成功/失败都发） | `tool_name`、`tool_result` | chat/research |
| `skill_active` | 本轮激活的 skill | `content`（skill 名列表 JSON） | chat/research |
| `budget_update` | 上下文预算快照 | `budget: {total, fraction, window}` | chat/research |
| `sandbox_update` | 沙箱活动（文件/bash） | `content` | 有沙箱工具时 |
| `error` | 流内错误（异常类型，非详情） | `content` | chat/research |
| `done` | 流终止标志；**客户端统一以 done 判定结束** | `content: ""` | chat/research（最后一帧） |

终态语义：正常结束以 `done` 收尾；流内错误先发 `error` 再发 `done`。客户端不得以连接关闭判定完成。

## 3. 断线续传

- 客户端持有最后收到的 `id`，重连同一端点时带请求头 `Last-Event-ID: <id>`。
- 服务端先补发缓冲中 `id` 之后的事件（at-least-once，可能重复——客户端按 id 幂等去重），再继续新流。
- 缺口超出缓冲容量（默认 500 帧/会话）时：
  - 响应头 `X-Engram-Events-Dropped: true`；
  - 流内先发一帧 `error`（`content: "resume gap exceeded buffer capacity"`）。
  客户端必须**明确告知用户**（提示重开会话），不得静默拼接。
- 网关重启后缓冲丢失：`Last-Event-ID` 之后的缺口无法补，同样走 dropped 语义。

## 4. 示例帧（机器可读）

以下 `sse` 代码块是**逐字节合法**的帧序列，供前后端测试提取解析。每块模拟一次完整流。

```sse
id: 1
event: skill_active
data: {"type": "skill_active", "content": "[\"find-skills\"]", "tool_name": null, "tool_args": null, "tool_result": null, "msg_id": null}

id: 2
event: thinking
data: {"type": "thinking", "content": "用户想要…", "tool_name": null, "tool_args": null, "tool_result": null, "msg_id": null}

id: 3
event: tool_start
data: {"type": "tool_start", "content": "", "tool_name": "bash", "tool_args": {"command": "echo hi"}, "tool_result": null, "msg_id": null}

id: 4
event: tool_end
data: {"type": "tool_end", "content": "", "tool_name": "bash", "tool_args": null, "tool_result": "hi", "msg_id": null}

id: 5
event: budget_update
data: {"type": "budget_update", "content": "", "tool_name": null, "tool_args": null, "tool_result": null, "msg_id": null, "budget": {"total": 120000, "fraction": 0.25, "window": "recent"}}

id: 6
event: answer
data: {"type": "answer", "content": "命令输出是 hi", "tool_name": null, "tool_args": null, "tool_result": null, "msg_id": "run1-msg2"}

id: 7
event: done
data: {"type": "done", "content": "", "tool_name": null, "tool_args": null, "tool_result": null, "msg_id": null}

```

```sse
id: 1
event: answer
data: {"type": "answer", "content": "部分回答…", "tool_name": null, "tool_args": null, "tool_result": null, "msg_id": null}

id: 2
event: error
data: {"type": "error", "content": "ProviderError", "tool_name": null, "tool_args": null, "tool_result": null, "msg_id": null}

id: 3
event: done
data: {"type": "done", "content": "", "tool_name": null, "tool_args": null, "tool_result": null, "msg_id": null}

```
