# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build & Development Commands

```bash
# Setup
uv venv .venv --python 3.11
uv pip install -e ".[all,dev]"

# Run
hermes                        # Interactive TUI
hermes chat -q "..."          # Single query
hermes-acp                    # ACP server mode

# Test (canonical, matches CI)
scripts/run_tests.sh
# Single file
pytest tests/path/to/test_file.py -v
# Single test
pytest tests/path/to/test_file.py::test_name -v

# Lint
ruff check .                  # Blocking (PLW1514 enforced)
uv tool run ty check          # Advisory type hints (non-blocking)
```

## Architecture

Hermes is a multi-model AI agent framework with messaging gateway integrations.

### Core Agent Loop
`run_agent.py` → `agent/conversation_loop.py` — ~3,900-line turn driver that handles LLM calls, tool dispatch, and context compression. Supports OpenAI-compatible APIs (Nous Portal, OpenRouter, Anthropic, Azure, Bedrock, Ollama) via a unified client abstraction.

### Tool System
42+ tools in `tools/` register themselves via `tools/registry.py`. Each tool is a class with a `run()` method. Categories: terminal execution, file ops, web search, vision, browser automation, code execution, subagent delegation. Heavy deps load lazily via `tools/lazy_deps.py`.

### Skills System
Procedural memory: bundled in `skills/`, optional in `optional-skills/`. The curator loop can create and improve skills automatically. Skills sync to an external Skills Hub.

### Messaging Gateway
`gateway/run.py` — routes messages from Telegram, Discord, Slack, WhatsApp, Signal, Matrix, DingTalk, Feishu, WeCom, Email, and SMS into the agent loop. Each platform has a session manager.

### Session & Memory
SQLite + FTS5 via `hermes_state.py`. Full-text search with LLM-powered recall. Supports Honcho AI dialectic memory and 7 optional backends. The agent degrades gracefully when SQLite lacks FTS5.

### Terminal Backends
Pluggable: local, Docker, SSH, Modal, Daytona. Selected at session init.

## Key Conventions

**Exact-pinned dependencies** — all deps use `==X.Y.Z` (hardened after a 2026-05-12 malicious-release incident). Never add version ranges. Update via `uv lock`.

**Windows encoding** — all file I/O must pass `encoding="utf-8"` explicitly. Enforced by ruff rule PLW1514.

**No POSIX-only APIs** — never use `os.kill`, `os.killpg`, or other POSIX-only syscalls. Use `psutil` for cross-platform process management.

**Test isolation** — `scripts/run_tests.sh` runs each test file in a subprocess. Module-level state does not persist across files. CI runs 6 parallel slices with duration-based load balancing.

**Lazy loading** — startup time matters (~100–300ms budget for imports). New heavy dependencies must be wrapped in `tools/lazy_deps.py` and loaded only on first use.
