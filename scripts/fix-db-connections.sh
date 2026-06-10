#!/bin/bash
#
# 一键修复所有数据库连接泄漏问题
# 为所有未关闭的 conn = kanban_db.connect() 添加 finally: conn.close()
#

set -e

ROUTES_DIR="/Users/a111/Documents/git/hermes-agent/hermes_kanban_server/routes"

echo "========================================="
echo "修复数据库连接泄漏"
echo "========================================="
echo ""

# 备份
echo "1. 创建备份..."
for file in tasks.py boards.py health.py; do
    cp "$ROUTES_DIR/$file" "$ROUTES_DIR/${file}.bak"
    echo "  ✅ 备份 $file -> ${file}.bak"
done

echo ""
echo "2. 修复连接泄漏..."

# 使用 Python 脚本精确修复
python3 << 'PYEOF'
import re
from pathlib import Path

routes_dir = Path("/Users/a111/Documents/git/hermes-agent/hermes_kanban_server/routes")

def fix_connection_leak(content):
    """为每个未关闭的连接添加 finally 块"""
    lines = content.split('\n')
    result = []
    i = 0

    while i < len(lines):
        line = lines[i]
        result.append(line)

        # 找到 conn = kanban_db.connect
        if 'conn = kanban_db.connect' in line:
            indent = len(line) - len(line.lstrip())

            # 检查接下来是否已经有 try
            if i + 1 < len(lines) and 'try:' in lines[i + 1]:
                # 已经有 try，跳过
                i += 1
                continue

            # 检查后面30行是否有 conn.close()
            has_close = False
            for j in range(i + 1, min(i + 30, len(lines))):
                if 'conn.close()' in lines[j]:
                    has_close = True
                    break

            if not has_close:
                # 需要修复
                # 添加 try
                result.append(' ' * indent + 'try:')

                # 收集到下一个 return 或 except 的所有行
                j = i + 1
                block_lines = []
                return_line_idx = None

                while j < len(lines):
                    current_line = lines[j]
                    current_indent = len(current_line) - len(current_line.lstrip()) if current_line.strip() else 999

                    # 找到 return 或 except（同级或更外层）
                    if current_indent <= indent and current_line.strip():
                        if 'return ' in current_line or 'except ' in current_line:
                            return_line_idx = j
                            break

                    block_lines.append(current_line)
                    j += 1

                # 添加块内代码（增加缩进）
                for block_line in block_lines:
                    if block_line.strip():
                        result.append('    ' + block_line)
                    else:
                        result.append(block_line)

                # 添加 finally
                result.append(' ' * indent + 'finally:')
                result.append(' ' * (indent + 4) + 'conn.close()')

                # 跳到 return 行（会在下一次循环添加）
                i = return_line_idx - 1 if return_line_idx else j - 1

        i += 1

    return '\n'.join(result)


# 修复每个文件
for filename in ["tasks.py", "boards.py", "health.py"]:
    filepath = routes_dir / filename
    content = filepath.read_text()

    # 统计
    connects_before = content.count('conn = kanban_db.connect')
    closes_before = content.count('conn.close()')

    # 修复
    fixed_content = fix_connection_leak(content)

    # 统计
    closes_after = fixed_content.count('conn.close()')

    # 写回
    filepath.write_text(fixed_content)

    print(f"✅ {filename}:")
    print(f"   Before: {connects_before} connects, {closes_before} closes")
    print(f"   After:  {connects_before} connects, {closes_after} closes")
    print(f"   Fixed:  {closes_after - closes_before} leaks")

PYEOF

echo ""
echo "3. 验证修复..."
python3 << 'PYEOF'
from pathlib import Path

routes_dir = Path("/Users/a111/Documents/git/hermes-agent/hermes_kanban_server/routes")

total_connects = 0
total_closes = 0

for filename in ["tasks.py", "boards.py", "health.py"]:
    filepath = routes_dir / filename
    content = filepath.read_text()

    connects = content.count('conn = kanban_db.connect')
    closes = content.count('conn.close()')

    total_connects += connects
    total_closes += closes

print(f"总计:")
print(f"  连接数: {total_connects}")
print(f"  关闭数: {total_closes}")

if total_connects == total_closes:
    print(f"  ✅ 所有连接都已正确关闭！")
else:
    print(f"  ❌ 还有 {total_connects - total_closes} 个连接未关闭")
PYEOF

echo ""
echo "========================================="
echo "修复完成！"
echo "========================================="
echo ""
echo "下一步:"
echo "  1. 重启服务器: kill <pid> && python3 -m hermes_kanban_server run --port 8650 &"
echo "  2. 测试API: curl http://localhost:8650/v1/boards/test-board/tasks"
echo "  3. 如有问题，恢复备份: cp routes/*.bak routes/"
echo ""
