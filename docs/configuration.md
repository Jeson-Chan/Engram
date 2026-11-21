# Engram 配置参考

> 本文件由扫描器自动生成，请勿手工编辑。
> 生成：`python -m engram.backend.app.cli.config_scanner`
> 校验（CI）：`python -m engram.backend.app.cli.config_scanner --check`

下表列出代码实际读取的全部环境变量。`.env.example` 只保留密钥与权力授予开关；
其余变量都有安全默认值，通常无需填写。Docker compose 路径下 DSN 与 Web 开关由
`docker-compose.yml` 注入，用户 `.env` 中不需要出现。

| 变量 | 默认值 | 读取模块 | 用途 |
|------|--------|----------|------|
| `ANTHROPIC_API_KEY` | — | `engram/backend/agents/config/provider_profile.py`<br>`engram/backend/agents/multiagent/credentials/pi_credential.py`<br>`engram/backend/agents/multiagent/runtimes/claude_code_runtime.py`<br>`engram/backend/agents/multiagent/runtimes/pi_runtime.py` | anthropic API 密钥 |
| `ANTHROPIC_AUTH_TOKEN` | — | `engram/backend/agents/multiagent/credentials/claude_credential.py`<br>`engram/backend/agents/multiagent/runtimes/claude_code_runtime.py` | Claude/Codex specialist 凭证 |
| `ANTHROPIC_BASE_URL` | https://api.anthropic.com | `engram/backend/agents/config/provider_profile.py` | anthropic API 端点 |
| `ANTHROPIC_ENABLED` | true | `engram/backend/agents/config/provider_config.py` | 单独禁用 anthropic（false=禁用） |
| `ANTHROPIC_MODEL` | claude-sonnet-4-20250514 | `engram/backend/agents/config/provider_profile.py` | anthropic 默认模型 |
| `CLAUDE_CODE_CREDENTIALS_PATH` | — | `engram/backend/agents/multiagent/credentials/claude_credential.py`<br>`engram/backend/agents/multiagent/runtimes/claude_code_runtime.py` | Claude/Codex specialist 凭证 |
| `CLAUDE_CODE_OAUTH_TOKEN` | — | `engram/backend/agents/multiagent/credentials/claude_credential.py`<br>`engram/backend/agents/multiagent/runtimes/claude_code_runtime.py` | Claude/Codex specialist 凭证 |
| `CODEX_AUTH_PATH` | — | `engram/backend/agents/multiagent/credentials/codex_credential.py`<br>`engram/backend/agents/multiagent/runtimes/codex_runtime.py` | Claude/Codex specialist 凭证 |
| `CODEX_HOME` | — | `engram/backend/agents/multiagent/runtimes/codex_runtime.py` | Claude/Codex specialist 凭证 |
| `DEEPSEEK_API_KEY` | — | `engram/backend/agents/config/provider_profile.py`<br>`engram/backend/agents/multiagent/credentials/pi_credential.py`<br>`engram/backend/agents/multiagent/runtimes/pi_runtime.py` | deepseek API 密钥 |
| `DEEPSEEK_BASE_URL` | https://api.deepseek.com | `engram/backend/agents/config/provider_profile.py` | deepseek API 端点 |
| `DEEPSEEK_ENABLED` | true | `engram/backend/agents/config/provider_config.py` | 单独禁用 deepseek（false=禁用） |
| `DEEPSEEK_MODEL` | deepseek-v4-flash | `engram/backend/agents/config/provider_profile.py` | deepseek 默认模型 |
| `ENGRAM_CHECKPOINT_DSN` | （空） | `engram/backend/agents/runtime/pg_checkpointer.py`<br>`engram/backend/app/cli/probes.py` | LangGraph 会话状态持久层 DSN（compose 注入） |
| `ENGRAM_GATEWAY_DB` | （空） | `engram/backend/app/gateway/session_store.py` | 网关会话库路径（SQLite） |
| `ENGRAM_GATEWAY_URL` | http://127.0.0.1:8000 | `engram/backend/app/tui/cockpit.py` | Engram 运行时配置 |
| `ENGRAM_INTERNAL_LLM_TIMEOUT` | 60 | `engram/backend/agents/middlewares/reflection_middleware.py` | 内部辅助 LLM 调用超时（秒） |
| `ENGRAM_LLM_MAX_RETRIES` | 1 | `engram/backend/agents/config/provider_config.py` | LLM SDK 重试次数 |
| `ENGRAM_LLM_REQUEST_TIMEOUT` | 120 | `engram/backend/agents/config/provider_config.py` | LLM 单请求超时（秒） |
| `ENGRAM_LOG_LEVEL` | INFO | `engram/backend/agents/memory/consolidation_worker.py` | Engram 运行时配置 |
| `ENGRAM_LOOP_DETECTION_ENABLED` | true | `engram/backend/agents/leader/factory.py` | 搜索循环保护总开关 |
| `ENGRAM_MCP_CONFIG_PATH` | .engram/mcp_servers.yaml / （表达式） | `engram/backend/agents/mcp/config.py`<br>`engram/backend/app/cli/probes.py` | MCP server 配置文件路径 |
| `ENGRAM_MCP_ENABLED` | false | `engram/backend/agents/mcp/__init__.py`<br>`engram/backend/app/cli/doctor.py`<br>`engram/backend/app/tui/settings_screen.py` | MCP 总开关（权力授予，默认关闭） |
| `ENGRAM_MEMORY_ENABLE_EXTRACT` | false | `engram/backend/agents/config/loader.py` | 实时抽取开关（after_model） |
| `ENGRAM_MEMORY_ENABLE_RECALL` | true | `engram/backend/agents/config/loader.py` | 记忆召回开关（before_model） |
| `ENGRAM_MEMORY_PG_DSN` | （空） | `engram/backend/agents/memory/strategies/default/strategy.py`<br>`engram/backend/app/cli/doctor.py`<br>`engram/backend/app/cli/probes.py`<br>`engram/backend/app/demo/seed.py` | 记忆冷层 Postgres DSN（compose 注入） |
| `ENGRAM_MEMORY_PHASE2_ENABLED` | false | `engram/backend/agents/config/loader.py`<br>`engram/backend/app/cli/doctor.py` | L5 自动沉淀（Phase 2） |
| `ENGRAM_MEMORY_PHASE2_TURNS` | 10 | `engram/backend/agents/config/loader.py` | 自动沉淀触发轮数 |
| `ENGRAM_MEMORY_STORAGE_PATH` | .engram/memory | `engram/backend/agents/config/loader.py` | 记忆 Markdown 持久化根目录 |
| `ENGRAM_MEMORY_TOKEN_BUDGET` | 2000 | `engram/backend/agents/config/loader.py` | 召回注入 token 预算上限 |
| `ENGRAM_MEMORY_TTL_SECONDS` | （空） | `engram/backend/agents/memory/adapters/redis_store.py` | 热层 TTL 覆盖（秒，测试/演示） |
| `ENGRAM_MEMORY_USE` | （空） | `engram/backend/agents/config/loader.py`<br>`engram/backend/app/cli/doctor.py` | 记忆主 Provider（空=禁用；default=Markdown+BM25） |
| `ENGRAM_MULTIAGENT_AUTO_APPROVE` | True | `engram/backend/agents/multiagent/config.py` | specialist 调用自动批准 |
| `ENGRAM_MULTIAGENT_DB_PATH` | .engram/multiagent.db | `engram/backend/agents/multiagent/config.py` | MultiAgent 配置 |
| `ENGRAM_MULTIAGENT_ENABLED` | True | `engram/backend/agents/multiagent/config.py`<br>`engram/backend/app/cli/doctor.py` | MultiAgent 总开关 |
| `ENGRAM_MULTIAGENT_HEALTH_THRESHOLD` | 0.4 | `engram/backend/agents/multiagent/config.py` | MultiAgent 配置 |
| `ENGRAM_MULTIAGENT_L2_COOLDOWN` | 3600.0 | `engram/backend/agents/multiagent/config.py` | MultiAgent 配置 |
| `ENGRAM_MULTIAGENT_L2_CRON_HOURS` | 6.0 | `engram/backend/agents/multiagent/config.py` | MultiAgent 配置 |
| `ENGRAM_MULTIAGENT_L2_ENABLED` | False | `engram/backend/agents/multiagent/config.py` | MultiAgent 配置 |
| `ENGRAM_MULTIAGENT_L2_MODEL` | — | `engram/backend/agents/multiagent/config.py` | MultiAgent 配置 |
| `ENGRAM_MULTIAGENT_L3_ENABLED` | False | `engram/backend/agents/multiagent/config.py` | MultiAgent 配置 |
| `ENGRAM_MULTIAGENT_L3_JUDGE_MODEL` | — | `engram/backend/agents/multiagent/config.py` | MultiAgent 配置 |
| `ENGRAM_MULTIAGENT_MAX_CONCURRENT` | 1 | `engram/backend/agents/multiagent/config.py` | MultiAgent 配置 |
| `ENGRAM_MULTIAGENT_MAX_STEPS` | 50 | `engram/backend/agents/multiagent/config.py` | MultiAgent 配置 |
| `ENGRAM_MULTIAGENT_MIN_INVOKED` | 5 | `engram/backend/agents/multiagent/config.py` | MultiAgent 配置 |
| `ENGRAM_MULTIAGENT_PI_API_KEY` | （空） | `engram/backend/agents/multiagent/config.py` | MultiAgent 配置 |
| `ENGRAM_MULTIAGENT_PI_AUTO_INSTALL` | True | `engram/backend/agents/multiagent/config.py` | MultiAgent 配置 |
| `ENGRAM_MULTIAGENT_PI_MODEL` | （空） | `engram/backend/agents/multiagent/config.py` | MultiAgent 配置 |
| `ENGRAM_MULTIAGENT_PI_PROVIDER` | （空） | `engram/backend/agents/multiagent/config.py` | MultiAgent 配置 |
| `ENGRAM_MULTIAGENT_PI_THINKING` | medium | `engram/backend/agents/multiagent/config.py` | MultiAgent 配置 |
| `ENGRAM_MULTIAGENT_SPECIALISTS` | — | `engram/backend/agents/multiagent/config.py` | 启用的 specialist 列表 |
| `ENGRAM_MULTIAGENT_SUBAGENT_MAX_STEPS` | 20 | `engram/backend/agents/multiagent/config.py` | MultiAgent 配置 |
| `ENGRAM_MULTIAGENT_SUBAGENT_TIMEOUT` | 300 | `engram/backend/agents/multiagent/config.py` | MultiAgent 配置 |
| `ENGRAM_MULTIAGENT_SUBAGENT_TOOL_GROUPS` | — | `engram/backend/agents/multiagent/config.py` | MultiAgent 配置 |
| `ENGRAM_MULTIAGENT_TIMEOUT` | 600 | `engram/backend/agents/multiagent/config.py` | MultiAgent 配置 |
| `ENGRAM_PG_DSN` | — | `engram/backend/agents/runtime/pg_checkpointer.py` | 网关 Postgres DSN |
| `ENGRAM_PROVIDER` | — | `engram/backend/app/gateway/views.py` | Engram 运行时配置 |
| `ENGRAM_REDIS_URL` | （空） | `engram/backend/agents/config/loader.py`<br>`engram/backend/app/cli/doctor.py`<br>`engram/backend/app/cli/probes.py`<br>`engram/backend/app/demo/seed.py` | 记忆热层 Redis URL（compose 注入） |
| `ENGRAM_RUNS_PG_DSN` | （空） | `engram/backend/app/demo/seed.py`<br>`engram/backend/app/gateway/main.py` | Run 记录 Postgres DSN |
| `ENGRAM_SANDBOX_ALLOW_HOST_BASH` | true | `engram/backend/agents/config/loader.py`<br>`engram/backend/app/cli/doctor.py` | Local 沙箱是否允许宿主机 bash |
| `ENGRAM_SANDBOX_BIND_HOST` | 127.0.0.1 | `engram/backend/agents/sandbox/docker/local_container_backend.py` | 沙箱配置 |
| `ENGRAM_SANDBOX_CONTAINER_PREFIX` | engram-sandbox | `engram/backend/agents/config/loader.py` | 沙箱容器名前缀 |
| `ENGRAM_SANDBOX_EXECUTOR` | local | `engram/backend/agents/config/loader.py` | 沙箱执行环境（local / wsl） |
| `ENGRAM_SANDBOX_HOST` | localhost | `engram/backend/agents/sandbox/docker/local_container_backend.py` | 沙箱配置 |
| `ENGRAM_SANDBOX_IDLE_TIMEOUT` | 600 | `engram/backend/agents/config/loader.py` | 沙箱空闲销毁秒数（0=不销毁） |
| `ENGRAM_SANDBOX_IMAGE` | all-in-one-sandbox:latest | `engram/backend/agents/config/loader.py` | Docker 沙箱镜像 |
| `ENGRAM_SANDBOX_PORT` | 18000 | `engram/backend/agents/config/loader.py` | 沙箱容器起始端口（占用时递增） |
| `ENGRAM_SANDBOX_REPLICAS` | 3 | `engram/backend/agents/config/loader.py` | 沙箱预热池大小（0=不预热） |
| `ENGRAM_SANDBOX_USE` | （空） | `engram/backend/agents/config/loader.py`<br>`engram/backend/app/cli/doctor.py` | 沙箱 provider 路径（空=未授权/禁用） |
| `ENGRAM_SANDBOX_WSL_DISTRO` | — | `engram/backend/agents/config/loader.py` | WSL 发行版名 |
| `ENGRAM_SANDBOX_WSL_USER` | — | `engram/backend/agents/config/loader.py` | WSL 执行用户 |
| `ENGRAM_SEARCH_HARD_LIMIT` | 20 | `engram/backend/agents/leader/factory.py` | 搜索硬上限（强制收尾） |
| `ENGRAM_SEARCH_SOFT_LIMIT` | 12 | `engram/backend/agents/leader/factory.py` | 搜索软上限（注入停止提醒） |
| `ENGRAM_SKILL_DB_PATH` | .engram/skills.db | `engram/backend/agents/skill/config.py` | Skill SQLite 路径 |
| `ENGRAM_SKILL_DIRS` | （空） | `engram/backend/agents/skill/config.py` | Skill 扫描目录（逗号分隔） |
| `ENGRAM_SKILL_ENABLED` | false | `engram/backend/agents/skill/config.py`<br>`engram/backend/app/cli/doctor.py`<br>`engram/backend/app/tui/settings_screen.py` | Skill 模块总开关 |
| `ENGRAM_SKILL_EVAL_ASYNC` | true | `engram/backend/agents/skill/config.py` | Skill 配置 |
| `ENGRAM_SKILL_EVAL_CAPTURED_MIN_SCORE` | 0.5 | `engram/backend/agents/skill/config.py` | Skill 配置 |
| `ENGRAM_SKILL_EVAL_CONTRACT_CHECK` | true | `engram/backend/agents/skill/config.py` | Skill 配置 |
| `ENGRAM_SKILL_EVAL_DEGRADATION_DELTA` | 0.15 | `engram/backend/agents/skill/config.py` | Skill 配置 |
| `ENGRAM_SKILL_EVAL_ENABLED` | false | `engram/backend/agents/skill/config.py` | Skill 配置 |
| `ENGRAM_SKILL_EVAL_JUDGMENT_ENABLED` | true | `engram/backend/agents/skill/config.py` | Skill 配置 |
| `ENGRAM_SKILL_EVAL_MAX_MESSAGES_CHARS` | 80000 | `engram/backend/agents/skill/config.py` | Skill 配置 |
| `ENGRAM_SKILL_EVAL_RUNTIME_WINDOW` | 20 | `engram/backend/agents/skill/config.py` | Skill 配置 |
| `ENGRAM_SKILL_EVAL_SKIP_NO_SKILL` | true | `engram/backend/agents/skill/config.py` | Skill 配置 |
| `ENGRAM_SKILL_EVAL_TASK_JUDGE_ENABLED` | true | `engram/backend/agents/skill/config.py` | Skill 配置 |
| `ENGRAM_SKILL_EVAL_TASK_WEIGHTS` | 0.50,0.35,0.05,0.10 | `engram/backend/agents/skill/config.py` | Skill 配置 |
| `ENGRAM_SKILL_EVOLVE_COOLDOWN_TURNS` | 10 | `engram/backend/agents/skill/config.py` | Skill 配置 |
| `ENGRAM_SKILL_EVOLVE_ENABLED` | false | `engram/backend/agents/skill/config.py` | Skill 配置 |
| `ENGRAM_SKILL_EVOLVE_MAX_STEPS` | 5 | `engram/backend/agents/skill/config.py` | Skill 配置 |
| `ENGRAM_SKILL_EVOLVE_MIN_SELECTIONS` | 5 | `engram/backend/agents/skill/config.py` | Skill 配置 |
| `ENGRAM_SKILL_EVOLVE_MUTATE_BUDGET` | 20 | `engram/backend/agents/skill/config.py` | Skill 配置 |
| `ENGRAM_SKILL_EVOLVE_THRESHOLD` | 0.3 | `engram/backend/agents/skill/config.py` | Skill 配置 |
| `ENGRAM_SKILL_HUB_AUDIT` | true | `engram/backend/agents/skill/config.py` | Skill 配置 |
| `ENGRAM_SKILL_HUB_ENABLED` | true | `engram/backend/agents/skill/config.py` | Skill 配置 |
| `ENGRAM_SKILL_HUB_QUARANTINE` | true | `engram/backend/agents/skill/config.py` | Skill 配置 |
| `ENGRAM_SKILL_INCLUDE_BUILTIN` | true | `engram/backend/agents/skill/config.py` | 是否加载 builtin skill |
| `ENGRAM_SKILL_MAX_INJECT` | 3 | `engram/backend/agents/skill/config.py` | 单轮最多注入 skill 数 |
| `ENGRAM_SKILL_MIN_SELECTIONS` | 5 | `engram/backend/agents/skill/config.py` | 淘汰判定最少命中数 |
| `ENGRAM_SKILL_QUALITY_THRESHOLD` | 0.3 | `engram/backend/agents/skill/config.py` | skill 质量淘汰阈值 |
| `ENGRAM_WEB_UI_DIST` | （空） | `engram/backend/app/gateway/web_ui.py` | Web 构建产物目录 |
| `ENGRAM_WEB_UI_ENABLED` | （空） | `engram/backend/app/cli/doctor.py`<br>`engram/backend/app/gateway/web_ui.py` | Web 工作台静态挂载开关 |
| `FAKE_BASE_URL` | （空） | `engram/backend/agents/config/provider_profile.py` | fake API 端点 |
| `FAKE_ENABLED` | true | `engram/backend/agents/config/provider_config.py` | 单独禁用 fake（false=禁用） |
| `FAKE_MODEL` | fake-chat | `engram/backend/agents/config/provider_profile.py` | fake 默认模型 |
| `GEMINI_API_KEY` | — | `engram/backend/agents/config/provider_profile.py`<br>`engram/backend/agents/multiagent/credentials/pi_credential.py`<br>`engram/backend/agents/multiagent/runtimes/pi_runtime.py` | gemini API 密钥 |
| `GEMINI_BASE_URL` | https://generativelanguage.googleapis.com/v1beta | `engram/backend/agents/config/provider_profile.py` | gemini API 端点 |
| `GEMINI_ENABLED` | true | `engram/backend/agents/config/provider_config.py` | 单独禁用 gemini（false=禁用） |
| `GEMINI_MODEL` | gemini-2.0-flash | `engram/backend/agents/config/provider_profile.py` | gemini 默认模型 |
| `GITHUB_TOKEN` | — | `engram/backend/agents/skill/hub/sources/github_source.py` | 见读取模块 |
| `GROQ_API_KEY` | — | `engram/backend/agents/multiagent/credentials/pi_credential.py`<br>`engram/backend/agents/multiagent/runtimes/pi_runtime.py` | API 密钥 |
| `KIMI_API_KEY` | — | `engram/backend/agents/multiagent/credentials/pi_credential.py`<br>`engram/backend/agents/multiagent/runtimes/pi_runtime.py` | API 密钥 |
| `MINIMAX_API_KEY` | — | `engram/backend/agents/multiagent/credentials/pi_credential.py`<br>`engram/backend/agents/multiagent/runtimes/pi_runtime.py` | API 密钥 |
| `MISTRAL_API_KEY` | — | `engram/backend/agents/multiagent/credentials/pi_credential.py`<br>`engram/backend/agents/multiagent/runtimes/pi_runtime.py` | API 密钥 |
| `MOONSHOT_API_KEY` | — | `engram/backend/agents/config/provider_profile.py` | moonshot API 密钥 |
| `MOONSHOT_BASE_URL` | https://api.moonshot.cn/v1 | `engram/backend/agents/config/provider_profile.py` | moonshot API 端点 |
| `MOONSHOT_ENABLED` | true | `engram/backend/agents/config/provider_config.py` | 单独禁用 moonshot（false=禁用） |
| `MOONSHOT_MODEL` | moonshot-v1-128k | `engram/backend/agents/config/provider_profile.py` | moonshot 默认模型 |
| `NVIDIA_API_KEY` | — | `engram/backend/agents/config/provider_profile.py` | nvidia API 密钥 |
| `NVIDIA_BASE_URL` | https://integrate.api.nvidia.com/v1 | `engram/backend/agents/config/provider_profile.py` | nvidia API 端点 |
| `NVIDIA_ENABLED` | true | `engram/backend/agents/config/provider_config.py` | 单独禁用 nvidia（false=禁用） |
| `NVIDIA_MODEL` | nvidia/llama-3.1-nemotron-70b-instruct | `engram/backend/agents/config/provider_profile.py` | nvidia 默认模型 |
| `OLLAMA_BASE_URL` | http://localhost:11434 | `engram/backend/agents/config/provider_profile.py` | ollama API 端点 |
| `OLLAMA_ENABLED` | true | `engram/backend/agents/config/provider_config.py` | 单独禁用 ollama（false=禁用） |
| `OLLAMA_MODEL` | llama3.1 | `engram/backend/agents/config/provider_profile.py` | ollama 默认模型 |
| `OPENAI_API_KEY` | — | `engram/backend/agents/config/provider_profile.py`<br>`engram/backend/agents/multiagent/credentials/pi_credential.py`<br>`engram/backend/agents/multiagent/runtimes/codex_runtime.py`<br>`engram/backend/agents/multiagent/runtimes/pi_runtime.py` | openai API 密钥 |
| `OPENAI_BASE_URL` | （空） | `engram/backend/agents/config/provider_profile.py` | openai API 端点 |
| `OPENAI_ENABLED` | true | `engram/backend/agents/config/provider_config.py` | 单独禁用 openai（false=禁用） |
| `OPENAI_MODEL` | gpt-4.1-mini | `engram/backend/agents/config/provider_profile.py` | openai 默认模型 |
| `OPENROUTER_API_KEY` | — | `engram/backend/agents/config/provider_profile.py`<br>`engram/backend/agents/multiagent/credentials/pi_credential.py`<br>`engram/backend/agents/multiagent/runtimes/pi_runtime.py` | openrouter API 密钥 |
| `OPENROUTER_BASE_URL` | https://openrouter.ai/api/v1 | `engram/backend/agents/config/provider_profile.py` | openrouter API 端点 |
| `OPENROUTER_ENABLED` | true | `engram/backend/agents/config/provider_config.py` | 单独禁用 openrouter（false=禁用） |
| `OPENROUTER_MODEL` | anthropic/claude-sonnet-4 | `engram/backend/agents/config/provider_profile.py` | openrouter 默认模型 |
| `PI_CODING_AGENT_DIR` | — | `engram/backend/agents/multiagent/credentials/pi_credential.py`<br>`engram/backend/agents/multiagent/runtimes/pi_runtime.py` | 见读取模块 |
| `QWEN_API_KEY` | — | `engram/backend/agents/config/provider_profile.py` | qwen API 密钥 |
| `QWEN_BASE_URL` | https://dashscope.aliyuncs.com/compatible-mode/v1 | `engram/backend/agents/config/provider_profile.py` | qwen API 端点 |
| `QWEN_ENABLED` | true | `engram/backend/agents/config/provider_config.py` | 单独禁用 qwen（false=禁用） |
| `QWEN_MODEL` | qwen-plus | `engram/backend/agents/config/provider_profile.py` | qwen 默认模型 |
| `TAVILY_API_KEY` | （空） | `engram/backend/agents/agent_tools/builtin/tavily_search.py`<br>`engram/backend/app/cli/doctor.py`<br>`engram/backend/app/cli/probes.py` | Tavily 联网搜索密钥（留空回退 DuckDuckGo） |
| `TOGETHER_API_KEY` | — | `engram/backend/agents/multiagent/credentials/pi_credential.py`<br>`engram/backend/agents/multiagent/runtimes/pi_runtime.py` | API 密钥 |
| `XAI_API_KEY` | — | `engram/backend/agents/config/provider_profile.py`<br>`engram/backend/agents/multiagent/credentials/pi_credential.py`<br>`engram/backend/agents/multiagent/runtimes/pi_runtime.py` | xai API 密钥 |
| `XAI_BASE_URL` | https://api.x.ai/v1 | `engram/backend/agents/config/provider_profile.py` | xai API 端点 |
| `XAI_ENABLED` | true | `engram/backend/agents/config/provider_config.py` | 单独禁用 xai（false=禁用） |
| `XAI_MODEL` | grok-3 | `engram/backend/agents/config/provider_profile.py` | xai 默认模型 |
| `XIAOMI_API_KEY` | — | `engram/backend/agents/multiagent/credentials/pi_credential.py`<br>`engram/backend/agents/multiagent/runtimes/pi_runtime.py` | API 密钥 |
| `ZAI_API_KEY` | — | `engram/backend/agents/multiagent/credentials/pi_credential.py`<br>`engram/backend/agents/multiagent/runtimes/pi_runtime.py` | API 密钥 |
| `ZHIPU_API_KEY` | — | `engram/backend/agents/config/provider_profile.py` | zhipu API 密钥 |
| `ZHIPU_BASE_URL` | https://open.bigmodel.cn/api/paas/v4 | `engram/backend/agents/config/provider_profile.py` | zhipu API 端点 |
| `ZHIPU_ENABLED` | true | `engram/backend/agents/config/provider_config.py` | 单独禁用 zhipu（false=禁用） |
| `ZHIPU_MODEL` | glm-4-plus | `engram/backend/agents/config/provider_profile.py` | zhipu 默认模型 |
