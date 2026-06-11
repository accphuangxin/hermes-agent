#!/bin/bash
# 开发模式启动所有 Hermes 服务

set -e

cd "$(dirname "$0")"

echo "════════════════════════════════════════════════════════════"
echo "  🚀 启动 Hermes 开发环境（所有服务）"
echo "════════════════════════════════════════════════════════════"
echo ""

# 检查虚拟环境
if [ -z "$VIRTUAL_ENV" ]; then
    if [ -f ".venv/bin/activate" ]; then
        echo "📌 激活虚拟环境..."
        source .venv/bin/activate
    else
        echo "❌ 虚拟环境不存在，请先运行："
        echo "   ./setup_dev_env.sh"
        exit 1
    fi
fi

# 清理旧进程
echo "🧹 清理旧进程..."
pkill -f "hermes_kanban_server" 2>/dev/null || true
pkill -f "hermes-agent-manager" 2>/dev/null || true
sleep 2

# 停止 launchd 管理的 gateway（避免与开发版冲突）
echo ""
echo "0️⃣  停止 launchd gateway（切换到开发版）..."
launchctl stop ai.hermes.gateway 2>/dev/null || true
launchctl unload ~/Library/LaunchAgents/ai.hermes.gateway.plist 2>/dev/null || true
pkill -f "hermes_cli.main gateway run" 2>/dev/null || true
sleep 1

# 启动 Agent Manager (后台)
echo ""
echo "1️⃣  启动 Agent Manager..."
if command -v hermes-agent-manager &> /dev/null; then
    hermes-agent-manager start || true
    echo "   ✅ Agent Manager 已启动"
else
    echo "   ⚠️  hermes-agent-manager 未安装，跳过"
fi

# 启动开发版 Gateway（使用本地 .venv，包含最新代码）
echo ""
echo "1.5️⃣  启动开发版 Gateway..."
python -m hermes_cli.main gateway run --replace > ~/.hermes/logs/gateway-dev.log 2>&1 &
GATEWAY_PID=$!
echo "   ✅ Gateway 已启动 (PID: $GATEWAY_PID)"
sleep 2

# 启动 Kanban API Server (前台，便于查看日志)
echo ""
echo "2️⃣  启动 Kanban API Server..."
if command -v hermes-kanban-server &> /dev/null; then
    echo "   📝 端口: 8650"
    echo "   🔄 修改代码后：按 Ctrl+C 停止，重新运行此脚本"
    echo ""
    echo "════════════════════════════════════════════════════════════"
    echo ""

    hermes-kanban-server run --port 8650
else
    echo "   ⚠️  hermes-kanban-server 未安装"
    echo ""
    echo "请先运行："
    echo "   uv pip install -e \".[all,dev]\""
    exit 1
fi
