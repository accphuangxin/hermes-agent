#!/bin/bash
# Hermes Agent 开发环境一键配置脚本

set -e

cd "$(dirname "$0")"

echo "════════════════════════════════════════════════════════════"
echo "  🔧 Hermes Agent 开发环境配置"
echo "════════════════════════════════════════════════════════════"
echo ""

# 1. 检查虚拟环境
if [ ! -d ".venv" ]; then
    echo "📦 创建虚拟环境..."
    uv venv .venv --python 3.11
else
    echo "✅ 虚拟环境已存在"
fi

# 2. 激活虚拟环境提示
echo ""
echo "⚠️  请先激活虚拟环境："
echo "   source .venv/bin/activate"
echo ""
echo "然后运行以下命令安装："
echo "   uv pip install -e \".[all,dev]\""
echo ""

# 3. 检查是否在虚拟环境中
if [ -z "$VIRTUAL_ENV" ]; then
    echo "❌ 虚拟环境未激活，请先运行："
    echo "   source .venv/bin/activate"
    echo ""
    echo "然后重新运行此脚本，或直接运行："
    echo "   uv pip install -e \".[all,dev]\""
    exit 1
fi

# 4. 安装可编辑模式
echo "📦 安装 Hermes Agent（可编辑模式）..."
uv pip install -e ".[all,dev]"

echo ""
echo "════════════════════════════════════════════════════════════"
echo "  ✅ 开发环境配置完成！"
echo "════════════════════════════════════════════════════════════"
echo ""
echo "现在你可以："
echo "  1. 修改代码后无需重新安装"
echo "  2. 直接运行命令测试："
echo ""
echo "     hermes                           # CLI"
echo "     hermes-agent-manager status      # Agent Manager"
echo "     hermes-kanban-server run         # Kanban API"
echo ""
echo "  3. 使用开发脚本："
echo ""
echo "     ./dev_all.sh                     # 启动所有服务"
echo "     ./dev_kanban_server.sh          # 只启动 Kanban API"
echo ""
echo "════════════════════════════════════════════════════════════"
