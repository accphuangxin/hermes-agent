# Hermes Agent config.yaml 配置项说明

> 配置文件路径：`~/.hermes/config.yaml`
> 修改后需重启 hermes 或 `hermes gateway restart` 生效。

---

## 目录

1. [模型配置](#1-模型配置)
2. [Agent 行为](#2-agent-行为)
3. [终端后端](#3-终端后端)
4. [Web 搜索](#4-web-搜索)
5. [浏览器自动化](#5-浏览器自动化)
6. [检查点快照](#6-检查点快照)
7. [工具输出限制](#7-工具输出限制)
8. [工具循环防护](#8-工具循环防护)
9. [上下文压缩](#9-上下文压缩)
10. [提示缓存](#10-提示缓存)
11. [辅助模型](#11-辅助模型)
12. [显示与 UI](#12-显示与-ui)
13. [TTS 语音合成](#13-tts-语音合成)
14. [STT 语音识别](#14-stt-语音识别)
15. [语音输入](#15-语音输入)
16. [内存与记忆](#16-内存与记忆)
17. [子 Agent 委托](#17-子-agent-委托)
18. [消息平台](#18-消息平台)
19. [Kanban 任务板](#19-kanban-任务板)
20. [安全与审批](#20-安全与审批)
21. [会话管理](#21-会话管理)
22. [Skills 技能](#22-skills-技能)
23. [其他配置](#23-其他配置)

---

## 1. 模型配置

```yaml
model:
  default: qwen3_6          # 默认使用的模型名称
  provider: custom          # 模型提供商（custom/openrouter/anthropic/bedrock 等）
  base_url: http://...      # 自定义 API 地址（provider=custom 时必填）
  api_key: sk-xxx           # API 密钥

providers: {}               # 额外的提供商配置（新格式，通常留空）
fallback_providers: []      # 备用提供商链，主模型失败时自动切换
credential_pool_strategies: {}  # 凭证轮换策略（fill_first/round_robin/random）

toolsets:
- hermes-cli                # 启用的工具集，hermes-cli 是基础工具集

custom_providers:           # 自定义 OpenAI 兼容提供商列表
- name: CloudCI             # 提供商名称（在请求 body 的 model 字段引用）
  base_url: http://...      # API 地址
  api_key: sk-xxx           # API 密钥
  model: qwen3_6            # 该提供商的默认模型
```

**fallback_providers 示例：**
```yaml
fallback_providers:
  - provider: openrouter
    model: anthropic/claude-sonnet-4
```
主模型遇到限流（429）、过载（529）、服务错误（503）或连接失败时自动切换。

---

## 2. Agent 行为

```yaml
agent:
  max_turns: 90
  # 每次对话最大工具调用轮数。超出后 agent 停止并提示用户。
  # 复杂任务建议 90~150，简单问答可设低。

  gateway_timeout: 1800
  # 通过消息平台（微信/Telegram等）触发的任务最大执行时间（秒）。
  # 0 = 无限制。默认 30 分钟。

  restart_drain_timeout: 180
  # gateway 停止/重启时，等待当前任务优雅结束的时间（秒）。
  # 0 = 立即中断。

  api_max_retries: 3
  # LLM API 调用失败时的最大重试次数。

  service_tier: ''
  # 服务等级（部分提供商支持，如 openai 的 "flex"/"default"）。空 = 不指定。

  tool_use_enforcement: auto
  # 是否强制 LLM 使用工具格式。
  # auto = 自动判断，true = 强制，false = 不强制，也可填模型名列表。

  task_completion_guidance: true
  # 是否在系统提示中注入"完成任务"引导语（约 80 tokens）。

  environment_probe: true
  # 启动时自动探测本地环境（Python/pip/uv/Node.js 等），
  # 结果注入系统提示让 agent 了解当前环境。

  environment_hint: ''
  # 手动补充环境描述，追加到系统提示末尾。

  gateway_timeout_warning: 900
  # 任务执行超过此秒数时，提前向用户发送"即将超时"警告。0 = 禁用。

  clarify_timeout: 600
  # agent 调用 clarify 工具等待用户回复的最大时间（秒）。

  gateway_notify_interval: 180
  # 长任务执行期间，每隔多少秒向用户发送"仍在处理中"通知。0 = 禁用。

  gateway_auto_continue_freshness: 3600
  # 自动继续标记的有效期（秒）。超出此时间的旧标记会被忽略。

  image_input_mode: auto
  # 用户发来图片时的处理方式。
  # auto = 自动判断，native = 原生图像输入，text = 转为文字描述。

  disabled_toolsets: []
  # 禁用的工具集列表，比如 ["terminal"] 可禁止 agent 执行终端命令。
```

---

## 3. 终端后端

```yaml
terminal:
  backend: local
  # 命令执行后端。可选：
  # local       - 直接在本机执行（默认）
  # docker      - 在 Docker 容器中执行（隔离环境）
  # ssh         - 在远程机器上执行
  # modal       - 在 Modal 云沙箱中执行（无服务器）
  # singularity - HPC 环境容器（Linux）
  # daytona     - Daytona 云开发环境

  modal_mode: auto
  # Modal 计费模式：auto/managed（Nous订阅）/direct（自己的Modal账号）

  cwd: .
  # gateway 会话的工作目录（点表示当前目录）。
  # CLI/TUI 模式始终使用启动时的目录，此配置只影响消息平台触发的任务。

  timeout: 180
  # 单条终端命令的执行超时（秒）。

  env_passthrough: []
  # 传递给沙箱/容器的宿主机环境变量名列表。

  shell_init_files: []
  # 额外的 shell 初始化文件路径（支持 ~ 和 ${VAR}）。

  auto_source_bashrc: true
  # 是否自动加载 ~/.profile、~/.bash_profile、~/.bashrc。

  persistent_shell: true
  # 跨多次 execute() 调用保持同一个 shell 进程（变量、cd 等状态保留）。

  # ── Docker 专属配置 ──
  docker_image: nikolaik/python-nodejs:python3.11-nodejs20
  docker_forward_env: []        # 转发到容器的宿主机环境变量
  docker_env: {}                # 容器内的固定环境变量
  docker_volumes: []            # 卷挂载，格式：["宿主路径:容器路径"]
  docker_mount_cwd_to_workspace: false  # 把宿主 cwd 挂载到容器 /workspace
  docker_extra_args: []         # 传给 docker run 的额外参数
  docker_run_as_host_user: false  # 用宿主 UID:GID 运行容器（避免权限问题）

  # ── 容器通用资源配置（Docker/Modal/Singularity/Daytona 共用）──
  container_cpu: 1              # CPU 核心数
  container_memory: 5120        # 内存（MB），默认 5GB
  container_disk: 51200         # 磁盘（MB），默认 50GB
  container_persistent: true   # 跨会话持久化文件系统

  # ── 其他后端镜像 ──
  singularity_image: docker://nikolaik/python-nodejs:python3.11-nodejs20
  modal_image: nikolaik/python-nodejs:python3.11-nodejs20
  daytona_image: nikolaik/python-nodejs:python3.11-nodejs20
```

---

## 4. Web 搜索

```yaml
web:
  backend: ''
  # 同时设置 web_search 和 web_extract 后端。
  # 可选：exa / parallel / firecrawl / tavily / searxng

  search_backend: ''
  # 仅覆盖搜索后端（优先级高于 backend）。

  extract_backend: ''
  # 仅覆盖网页提取后端（优先级高于 backend）。
```

各后端需要对应的 API Key（在 `.env` 中设置）：`EXA_API_KEY`、`TAVILY_API_KEY`、`FIRECRAWL_API_KEY`、`SEARXNG_URL` 等。

---

## 5. 浏览器自动化

```yaml
browser:
  inactivity_timeout: 120     # 浏览器无操作自动关闭（秒）
  command_timeout: 30         # 单条浏览器命令超时（秒）
  record_sessions: false      # 自动录制浏览器操作为 WebM 视频
  allow_private_urls: false   # 是否允许访问内网/私有 IP（如 192.168.x.x）
  engine: auto                # 浏览器引擎：auto/chrome/lightpanda
  auto_local_for_private_urls: true  # 云环境下访问内网时自动切换本地 Chromium
  cdp_url: ''                 # 持久 Chrome DevTools Protocol 端点（空=每次新建）
  dialog_policy: must_respond # 弹窗处理策略：
                              #   must_respond  - 必须等待 agent 处理
                              #   auto_dismiss  - 自动关闭
                              #   auto_accept   - 自动确认

  dialog_timeout_s: 300       # 弹窗自动处理超时（秒）

  camofox:                    # Camofox 浏览器服务配置
    managed_persistence: false    # 使用稳定的 Camofox 配置文件
    user_id: ''                   # 外部管理的用户 ID
    session_key: ''               # 会话密钥
    adopt_existing_tab: false     # 复用已有 tab
    rewrite_loopback_urls: false  # 重写 loopback 地址为别名
    loopback_host_alias: host.docker.internal  # loopback 别名
```

---

## 6. 检查点快照

```yaml
checkpoints:
  enabled: false          # 是否启用文件系统检查点（类似 git，可回滚文件变更）
  max_snapshots: 20       # 每个工作目录保留的最大检查点数
  max_total_size_mb: 500  # 所有检查点总大小上限（MB），0=不限
  max_file_size_mb: 10    # 单个文件大小上限（MB），0=不限
  auto_prune: true        # 自动清理过期和孤立的检查点
  retention_days: 7       # 检查点保留天数
  delete_orphans: true    # 删除工作目录已不存在的检查点
  min_interval_hours: 24  # 自动维护最小间隔（小时）
```

---

## 7. 工具输出限制

```yaml
file_read_max_chars: 100000
# 单次 read_file 调用返回的最大字符数（约 100KB）。

tool_output:
  max_bytes: 50000       # 终端命令输出的最大字节数
  max_lines: 2000        # 文件读取分页的最大行数
  max_line_length: 2000  # 带行号视图中每行最大字符数
```

---

## 8. 工具循环防护

防止 agent 陷入无效重复调用的保护机制。

```yaml
tool_loop_guardrails:
  warnings_enabled: true   # 触发阈值时向 agent 发出警告（软提示）
  hard_stop_enabled: false  # 触发阈值时直接中止任务（硬停止）

  warn_after:             # 触发警告的阈值
    exact_failure: 2      # 同一工具调用连续失败 N 次
    same_tool_failure: 3  # 同类工具累计失败 N 次
    idempotent_no_progress: 2  # 幂等操作无进展 N 次

  hard_stop_after:        # 触发硬停止的阈值（需 hard_stop_enabled: true）
    exact_failure: 5
    same_tool_failure: 8
    idempotent_no_progress: 5
```

---

## 9. 上下文压缩

当对话历史过长时自动压缩，避免超出模型上下文窗口。

```yaml
compression:
  enabled: true           # 是否启用自动压缩
  threshold: 0.5          # 上下文使用率超过此比例时触发压缩（0.5 = 50%）
  target_ratio: 0.2       # 压缩后保留最近 20% 的内容作为尾部
  protect_last_n: 20      # 最近 N 条消息不参与压缩
  protect_first_n: 3      # 最前 N 条消息不参与压缩（保留初始指令）
  hygiene_hard_message_limit: 400  # 消息数超过此值时强制压缩
  abort_on_summary_failure: false  # 压缩摘要生成失败时是否中止（false=跳过）
```

---

## 10. 提示缓存

```yaml
prompt_caching:
  cache_ttl: 5m
  # 缓存生存时间。支持：5m（5分钟）/ 1h（1小时）。
  # 仅 Anthropic 原生 API 支持，可显著降低重复提示的 token 费用。
```

---

## 11. 辅助模型

为不同子任务指定独立的 LLM（不填则继承主模型）。

所有辅助任务共享相同的配置字段：

```yaml
auxiliary:
  vision:              # 图像分析（看图、截图理解）
    provider: auto     # auto = 自动选择，也可指定 openrouter/anthropic 等
    model: ''          # 模型名，空 = 继承主模型
    base_url: ''       # API 地址，空 = 继承主模型
    api_key: ''        # API 密钥
    timeout: 120       # 请求超时（秒）
    extra_body: {}     # 额外的请求字段（提供商特定参数）
    download_timeout: 30  # 图片下载超时（秒，仅 vision 有此字段）

  web_extract:         # 网页内容提取（总结网页）
    timeout: 360       # 网页提取通常较慢，默认 6 分钟

  compression:         # 生成对话历史摘要（上下文压缩用）
    timeout: 120

  skills_hub:          # Skills Hub 智能推荐
    timeout: 30

  approval:            # 危险操作审批判断
    timeout: 30

  mcp:                 # MCP 工具调用辅助
    timeout: 30

  title_generation:    # 自动生成会话标题
    timeout: 30

  triage_specifier:    # Kanban 任务分类路由
    timeout: 120

  kanban_decomposer:   # Kanban 任务分解
    timeout: 180

  profile_describer:   # Profile 描述生成
    timeout: 60

  curator:             # Skills 管理员（自动优化 skill）
    timeout: 600
```

---

## 12. 显示与 UI

```yaml
display:
  compact: false
  # 紧凑模式：减少空行和装饰性输出。

  personality: kawaii
  # UI 风格/人格，影响 emoji 和提示语风格。

  language: en
  # 界面语言：en/zh/ja/de/es/fr/tr/uk

  skin: default
  # UI 皮肤主题。

  streaming: false
  # 是否流式输出 LLM 响应（逐字显示）。

  show_reasoning: false
  # 是否显示模型的思维链/推理过程（支持 thinking 的模型）。

  timestamps: false
  # 消息是否显示时间戳。

  show_cost: false
  # 是否在状态栏显示本次调用的 token 费用估算。

  final_response_markdown: strip
  # 最终回复的 markdown 处理方式：
  # strip  - 去除 markdown 符号，显示纯文本（默认）
  # render - 渲染 markdown
  # raw    - 原样显示

  inline_diffs: true
  # 文件修改时显示内联 diff 预览。

  file_mutation_verifier: true
  # 文件写入后自动验证是否成功，失败时显示警告。

  turn_completion_explainer: true
  # 异常完成（如超时、达到上限）时向用户解释原因。

  tool_progress: all
  # 工具调用进度显示级别：
  # off     - 不显示
  # new     - 仅在工具变化时显示
  # all     - 显示每次调用（默认）
  # verbose - 显示完整参数和返回值

  persistent_output: true
  # Ctrl+L 清屏后保留最近的输出。

  persistent_output_max_lines: 200
  # 清屏后保留的最大行数。

  busy_input_mode: interrupt
  # agent 执行中用户输入的处理方式：
  # interrupt - 中断当前任务（默认）
  # queue     - 排队等待完成后执行
  # steer     - 注入为引导消息

  bell_on_complete: false
  # agent 完成任务时是否响铃提示。

  tui_auto_resume_recent: false
  # TUI 启动时是否自动恢复最近的会话。

  tui_status_indicator: kaomoji
  # TUI 状态指示器风格：kaomoji / emoji / unicode / ascii

  interim_assistant_messages: true
  # 显示 agent 的中间状态消息（如"正在搜索..."）。

  tool_preview_length: 0
  # 工具调用参数预览的最大字符数，0 = 不限制。

  ephemeral_system_ttl: 0
  # 系统通知自动消失时间（秒），0 = 不自动消失。

  copy_shortcut: auto
  # 复制快捷键：auto / ctrl_c / ctrl_shift_c / disabled

  resume_display: full
  # 恢复会话时显示历史的方式：full / summary / none

  resume_exchanges: 10
  # 恢复时最多显示最近 N 轮对话。

  resume_max_user_chars: 300
  # 历史消息中用户消息的截断长度。

  resume_max_assistant_chars: 200
  # 历史消息中 assistant 消息的截断长度（最后一条不截断）。

  resume_max_assistant_lines: 3
  # 历史消息中 assistant 消息的最大显示行数。

  resume_skip_tool_only: true
  # 跳过只有工具调用、没有文字内容的历史条目。

  tool_progress_command: false
  # 启用 /verbose 命令（运行时切换工具进度显示级别）。

  user_message_preview:
    first_lines: 2             # 长消息预览显示前 N 行
    last_lines: 2              # 长消息预览显示后 N 行

  platforms: {}
  # 各平台的独立显示配置覆盖，如：
  # platforms:
  #   telegram:
  #     tool_progress: off

  runtime_footer:
    enabled: false             # 是否在每条回复末尾显示运行时信息
    fields:
    - model                   # 显示当前模型
    - context_pct             # 显示上下文使用率
    - cwd                     # 显示当前工作目录

dashboard:
  theme: default              # 仪表板主题
  show_token_analytics: false # 显示 token 用量和费用分析
  public_url: ''              # 反向代理时的公网 URL
  oauth:
    client_id: ''             # OAuth 客户端 ID
    portal_url: ''            # 门户地址

privacy:
  redact_pii: false
  # 在日志和响应中自动脱敏个人信息（电话号码、用户 ID 等哈希处理）。
```

---

## 13. TTS 语音合成

```yaml
tts:
  provider: edge
  # 当前使用的 TTS 提供商：
  # edge       - 微软 Edge TTS（免费，无需 Key）
  # elevenlabs - ElevenLabs（高质量，需 ELEVENLABS_API_KEY）
  # openai     - OpenAI TTS（需 OPENAI_API_KEY）
  # xai        - xAI TTS（需 XAI_API_KEY 或 OAuth）
  # minimax    - MiniMax TTS（需 MINIMAX_API_KEY）
  # mistral    - Mistral Voxtral（需 MISTRAL_API_KEY）
  # neutts     - NeuTTS 本地（离线，无需 Key，约 300MB 模型）
  # piper      - Piper 本地（轻量离线）

  edge:
    voice: en-US-AriaNeural   # Edge TTS 声音，中文可用 zh-CN-XiaoxiaoNeural

  elevenlabs:
    voice_id: pNInz6obpgDQGcFmaJgB
    model_id: eleven_multilingual_v2

  openai:
    model: gpt-4o-mini-tts
    voice: alloy              # alloy/echo/fable/onyx/nova/shimmer

  xai:
    voice_id: eve
    language: en
    sample_rate: 24000
    bit_rate: 128000

  mistral:
    model: voxtral-mini-tts-2603
    voice_id: c69964a6-ab8b-4f8a-9465-ec0925096ec8

  neutts:
    ref_audio: ''             # 参考音频路径（声音克隆用）
    ref_text: ''              # 参考文本路径
    model: neuphonic/neutts-air-q4-gguf
    device: cpu               # cpu / cuda / mps

  piper:
    voice: en_US-lessac-medium
```

---

## 14. STT 语音识别

```yaml
stt:
  enabled: true
  provider: local
  # 语音转文字提供商：
  # local  - 本地 faster-whisper（离线，需安装）
  # openai - OpenAI Whisper API
  # groq   - Groq Whisper API（快速）
  # mistral - Mistral STT

  local:
    model: base       # 模型大小：tiny/base/small/medium/large
    language: ''      # 强制语言（空 = 自动检测，zh = 中文）

  openai:
    model: whisper-1

  mistral:
    model: voxtral-mini-latest
```

---

## 15. 语音输入

```yaml
voice:
  record_key: ctrl+b          # 按住录音的快捷键
  max_recording_seconds: 120  # 最大录音时长（秒）
  auto_tts: false             # agent 回复时自动朗读
  beep_enabled: true          # 录音开始/结束提示音
  silence_threshold: 200      # 静音检测 RMS 阈值（值越大越不敏感）
  silence_duration: 3.0       # 静音持续此秒数后自动停止录音

human_delay:
  mode: 'off'
  # 模拟人类输入延迟（防检测用途）：
  # off    - 禁用（默认）
  # fixed  - 固定延迟
  # random - 在 min_ms~max_ms 之间随机
  min_ms: 800                 # 最小延迟（毫秒）
  max_ms: 2500                # 最大延迟（毫秒）
```

---

## 16. 内存与记忆

```yaml
context:
  engine: compressor
  # 上下文引擎：compressor（默认压缩器）或插件名称。

memory:
  memory_enabled: true        # 是否启用持久记忆（跨会话保留重要信息）
  user_profile_enabled: true  # 是否维护用户画像（记录用户偏好和背景）
  memory_char_limit: 2200     # 记忆内容最大字符数（约 800 tokens）
  user_char_limit: 1375       # 用户画像最大字符数（约 500 tokens）
  provider: ''                # 外部记忆提供商（空 = 本地 SQLite）
```

---

## 17. 子 Agent 委托

```yaml
delegation:
  model: ''         # 子 agent 使用的模型（空 = 继承主 agent 模型）
  provider: ''      # 子 agent 使用的提供商
  base_url: ''      # 子 agent 的 API 地址
  api_key: ''       # 子 agent 的 API 密钥
  api_mode: ''      # 协议格式：空/chat_completions/anthropic_messages/codex_responses

  inherit_mcp_toolsets: true   # 子 agent 是否继承父级 MCP 工具集

  max_iterations: 50           # 每个子 agent 的最大迭代轮数
  child_timeout_seconds: 600   # 子 agent 超时时间（秒），最小 30 秒

  reasoning_effort: ''         # 推理强度（支持 thinking 的模型）：low/medium/high

  max_concurrent_children: 3
  # 最多同时运行多少个子 agent（并发上限）。
  # 批量任务时建议提高，如 500条/50批 = 10个子 agent，设为 10。

  max_spawn_depth: 1
  # 子 agent 的最大嵌套深度（1~3）。
  # 1 = 只有一级子 agent，不能再生成孙 agent。

  orchestrator_enabled: true   # 是否允许 agent 扮演编排者角色

  subagent_auto_approve: false
  # 子 agent 执行危险命令时是否自动批准（谨慎开启）。
```

---

## 18. 消息平台

### Slack

```yaml
slack:
  require_mention: true        # 是否需要 @mention 才响应
  free_response_channels: ''   # 无需 @mention 的频道 ID（逗号分隔）
  allowed_channels: ''         # 白名单频道 ID（空 = 所有频道）
  channel_prompts: {}          # 各频道的独立系统提示，格式：{频道ID: "提示内容"}
```

### Discord

```yaml
discord:
  require_mention: true        # 需要 @mention
  free_response_channels: ''   # 无需 @mention 的频道
  allowed_channels: ''         # 白名单频道
  auto_thread: true            # 自动为每条消息创建线程
  thread_require_mention: false  # 线程内也需要 @mention
  history_backfill: true       # 启动时回填最近的频道消息
  history_backfill_limit: 50   # 回填消息数上限
  reactions: true              # 用表情回应消息（表示已收到）
  channel_prompts: {}          # 各频道独立系统提示
  dm_role_auth_guild: ''       # DM 鉴权时验证的 Guild ID
  server_actions: ''           # 允许的服务器操作
  allow_any_attachment: false  # 是否接受任意类型附件
  max_attachment_bytes: 33554432  # 附件大小上限（32 MiB）
```

### Telegram

```yaml
telegram:
  reactions: false             # 用表情回应消息
  channel_prompts: {}          # 各聊天独立系统提示
  allowed_chats: ''            # 白名单聊天 ID（空 = 允许所有）
```

### Mattermost

```yaml
mattermost:
  require_mention: true
  free_response_channels: ''
  allowed_channels: ''
  channel_prompts: {}
```

### Matrix

```yaml
matrix:
  require_mention: true
  free_response_rooms: ''      # 无需 @mention 的房间 ID
  allowed_rooms: ''            # 白名单房间 ID
```

### 平台通用配置（在 gateway.platforms 下）

```yaml
platforms:
  api_server:
    enabled: true
    cors_origins: '*'          # CORS 允许的来源
    key: root@123123           # API 鉴权 Key（请求头 Authorization: Bearer xxx）
    extra:
      host: 0.0.0.0            # 监听地址
      port: 8643               # 监听端口

  weixin:                      # 微信平台（通过 .env 中的 WEIXIN_TOKEN 等配置）
    extra:
      model: qwen3_6           # 该平台专用模型（覆盖全局 model）
      provider: CloudCI        # 该平台专用提供商
      base_url: http://...     # 该平台专用 LLM API 地址
      api_key: sk-xxx          # 该平台专用 API 密钥
```

### 会话重置策略

```yaml
session_reset:
  mode: both
  # 会话自动重置模式：
  # daily  - 每天固定时间重置
  # idle   - 空闲超时后重置
  # both   - 两者都触发（先到先得）
  # none   - 不自动重置

  idle_minutes: 1440   # 空闲超过此分钟数触发重置（1440=24小时）
  at_hour: 4           # 每日重置的小时（0~23，本地时间）
```

---

## 19. Kanban 任务板

```yaml
kanban:
  dispatch_in_gateway: true    # 在 gateway 进程中运行任务调度器
  dispatch_interval_seconds: 60  # 调度器轮询间隔（秒）
  failure_limit: 2             # 连续失败 N 次后自动阻止任务
  worker_log_rotate_bytes: 2097152  # 工作进程日志轮转大小（2MB）
  worker_log_backup_count: 1   # 保留的备份日志文件数

  orchestrator_profile: ''     # 分解复杂任务的专用 profile 名
  default_assignee: ''         # 未指定负责人时的默认 profile 名

  max_in_progress_per_profile: null  # 每个 profile 同时执行的最大任务数（null=不限）

  auto_decompose: true         # 自动分解 triage 状态的任务
  auto_decompose_per_tick: 3   # 每次调度最多分解 N 个任务

  dispatch_stale_timeout_seconds: 14400  # 任务执行超过此秒数（4小时）标记为陈旧

cron:
  wrap_response: true          # 定时任务结果是否加头尾包装
  max_parallel_jobs: null      # 最大并行定时任务数（null=不限）
```

---

## 20. 安全与审批

```yaml
approvals:
  mode: manual
  # 危险操作审批模式：
  # manual - 每次都提示用户确认（默认）
  # smart  - AI 判断是否需要确认
  # off    - 不需要确认（危险！）

  timeout: 60                  # 等待用户审批的超时时间（秒）
  cron_mode: deny              # 定时任务中遇到危险操作：deny=拒绝/approve=自动批准
  mcp_reload_confirm: true     # /reload-mcp 命令需要确认
  destructive_slash_confirm: true  # 破坏性斜杠命令需要确认

command_allowlist: []
# 永久允许的危险命令模式（正则表达式列表），无需每次确认。

security:
  allow_private_urls: false    # 允许访问内网/私有 IP
  redact_secrets: true         # 自动隐藏响应和日志中的敏感信息
  tirith_enabled: true         # 启用 Tirith 安全扫描
  tirith_path: tirith          # Tirith 二进制路径
  tirith_timeout: 5            # Tirith 扫描超时（秒）
  tirith_fail_open: true       # 扫描失败时是否允许继续（true=允许）
  allow_lazy_installs: true    # 允许运行时自动安装依赖包

  website_blocklist:
    enabled: false             # 启用网站黑名单
    domains: []                # 被阻止的域名列表
    shared_files: []           # 外部黑名单文件路径

  acked_advisories: []         # 已确认的安全公告 ID（不再重复提示）
```

---

## 21. 会话管理

```yaml
sessions:
  auto_prune: false            # 是否自动清理过期会话
  retention_days: 90           # 会话保留天数
  vacuum_after_prune: true     # 清理后执行 SQLite VACUUM（压缩数据库）
  min_interval_hours: 24       # 自动清理最小间隔（小时）
  write_json_snapshots: false  # 是否同时写入 JSON 格式快照（调试用）
```

---

## 22. Skills 技能

```yaml
skills:
  external_dirs: []            # 额外的外部 skill 目录路径
  template_vars: true          # 替换 SKILL.md 中的 ${HERMES_SKILL_DIR} 等变量
  inline_shell: false          # 是否预执行 SKILL.md 中的 !`cmd` 片段
  inline_shell_timeout: 10     # !`cmd` 执行超时（秒）
  guard_agent_created: false   # 对 agent 创建的 skill 进行安全扫描

curator:
  enabled: true                # 启用 Skill 管理员（自动优化和清理 skill）
  interval_hours: 168          # 管理员运行间隔（小时，默认每周一次）
  min_idle_hours: 2            # 系统空闲至少 N 小时才运行
  stale_after_days: 30         # N 天未使用的 skill 标记为陈旧
  archive_after_days: 90       # N 天未使用的 skill 自动归档
  backup:
    enabled: true              # 运行前备份 skill
    keep: 5                    # 保留最近 N 个备份快照
```

---

## 23. 其他配置

```yaml
timezone: ''
# IANA 时区（如 Asia/Shanghai），空 = 使用服务器本地时区。
# 影响定时任务触发时间和日志时间戳显示。

logging:
  level: INFO                  # 日志级别：DEBUG/INFO/WARNING/ERROR
  max_size_mb: 5               # 单个日志文件大小上限（MB）
  backup_count: 3              # 轮转备份文件数
  memory_monitor:
    enabled: true              # 启用内存监控日志
    interval_seconds: 300      # 内存使用情况记录间隔（秒）

network:
  force_ipv4: false            # 强制使用 IPv4（解决某些 IPv6 连接问题）

model_catalog:
  enabled: true                # 启用远程模型目录（获取最新模型列表）
  url: https://hermes-agent.nousresearch.com/docs/api/model-catalog.json
  ttl_hours: 24                # 模型目录缓存时间（小时）
  providers: {}                # 按提供商覆盖目录 URL

lsp:
  enabled: true                # 启用语言服务器（代码诊断和补全）
  wait_mode: document          # 等待模式：document/full
  wait_timeout: 5.0            # 等待诊断超时（秒）
  install_strategy: auto       # LSP 安装策略：auto/manual/off
  servers: {}                  # 各语言服务器的自定义配置

x_search:
  model: grok-4.20-reasoning   # xAI 搜索使用的模型
  timeout_seconds: 180         # 请求超时（秒）
  retries: 2                   # 失败重试次数

secrets:
  bitwarden:                   # Bitwarden Secrets Manager 集成
    enabled: false             # 是否启用
    access_token_env: BWS_ACCESS_TOKEN  # 访问令牌的环境变量名
    project_id: ''             # BSM 项目 UUID
    cache_ttl_seconds: 300     # 密钥缓存时间（秒）
    override_existing: true    # 是否覆盖已有的同名环境变量
    auto_install: true         # 是否自动安装 bws CLI
    server_url: ''             # 自部署 Bitwarden 服务器地址

updates:
  pre_update_backup: false     # hermes update 前自动备份 HERMES_HOME
  backup_keep: 5               # 保留最近 N 个更新备份

onboarding:
  seen: {}                     # 记录已显示过的新手引导提示（自动维护，勿手动修改）

# 粘贴处理配置
paste_collapse_threshold: 5           # 括号粘贴超过 N 行时折叠显示
paste_collapse_threshold_fallback: 5  # 回退模式的行数阈值
paste_collapse_char_threshold: 2000   # 单行超过 N 字符时折叠

code_execution:
  mode: project
  # 代码执行模式：
  # project - 允许访问项目文件（默认）
  # strict  - 严格沙箱，仅执行代码不访问文件系统

tools:
  tool_search:
    enabled: auto              # 工具搜索：auto/on/off
    threshold_pct: 10          # auto 模式下激活的工具集占比阈值（%）
    search_default_limit: 5    # 默认搜索结果数
    max_search_limit: 20       # 最大搜索结果数

quick_commands: {}
# 用户自定义快捷命令，格式：
# quick_commands:
#   r: "hermes gateway restart"
#   s: "hermes gateway status"

hooks: {}
# Shell 钩子，在特定事件时执行，格式：
# hooks:
#   PreToolUse: ["echo 'tool called'"]
#   PostToolUse: ["notify"]

hooks_auto_accept: false
# 是否自动接受新发现的钩子（不再提示确认）。

personalities: {}
# 自定义人格定义，覆盖默认的 kawaii 等风格。

honcho: {}
# Honcho AI 外部记忆服务配置（留空 = 不使用）。

prefill_messages_file: ''
# 临时的 prefill 消息文件路径（JSON 格式），用于调试或预置上下文。

goals:
  max_turns: 20
  # Goals 功能的最大继续轮数（/goal 命令触发的自主任务）。

_config_version: 24
# 配置文件格式版本，hermes 自动管理，勿手动修改。
```

---

## 快速参考：最常用配置

| 需求 | 配置项 | 示例值 |
|------|--------|--------|
| 换模型 | `model.default` | `claude-sonnet-4-6` |
| 换 API 地址 | `model.base_url` | `http://localhost:11434/v1` |
| 增加最大轮数 | `agent.max_turns` | `150` |
| 并行子 agent 数 | `delegation.max_concurrent_children` | `10` |
| 关闭上下文压缩 | `compression.enabled` | `false` |
| 切换界面语言 | `display.language` | `zh` |
| 设置工作目录 | `terminal.cwd` | `/Users/me/projects` |
| 子 agent 用不同模型 | `delegation.model` | `qwen3_6` |
| 每天定时重置会话 | `session_reset.mode` | `daily` |
| 允许某命令无需审批 | `command_allowlist` | `["rm -rf /tmp/*"]` |
