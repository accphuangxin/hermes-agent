#!/usr/bin/env bash
# 一键创建健康管家 profile，安装 health-guardian skill，写入专属人格
set -euo pipefail

PROFILE_NAME="${1:-health}"
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "==> 创建健康管家 profile: ${PROFILE_NAME}"

# 1. 创建 profile（如已存在则跳过）
if hermes profile list 2>/dev/null | grep -q "^${PROFILE_NAME}$"; then
    echo "    profile '${PROFILE_NAME}' 已存在，跳过创建"
else
    hermes profile create "${PROFILE_NAME}" \
        --description "个人健康管家，负责每日健康打卡、营养跟踪、运动建议、用药提醒和症状评估"
    echo "    ✅ profile 已创建"
fi

PROFILE_HOME="${HERMES_HOME:-${HOME}/.hermes}/profiles/${PROFILE_NAME}"
# 默认 profile 在 ~/.hermes 本身
if [[ "${PROFILE_NAME}" == "default" ]]; then
    PROFILE_HOME="${HERMES_HOME:-${HOME}/.hermes}"
fi

# 2. 安装 health-guardian skill
SKILLS_DIR="${PROFILE_HOME}/skills/health-guardian"
if [[ -d "${SKILLS_DIR}" ]]; then
    echo "    health-guardian skill 已安装，更新中..."
    rm -rf "${SKILLS_DIR}"
fi
cp -r "${SKILL_DIR}" "${SKILLS_DIR}"
echo "    ✅ health-guardian skill 已安装到 ${SKILLS_DIR}"

# 3. 写入专属人格
SOUL_DST="${PROFILE_HOME}/SOUL.md"
if [[ ! -f "${SOUL_DST}" ]]; then
    cp "${SKILL_DIR}/SOUL.md" "${SOUL_DST}"
    echo "    ✅ SOUL.md 已写入"
else
    echo "    SOUL.md 已存在，跳过（如需更新请手动替换 ${SOUL_DST}）"
fi

# 4. 确保 memories 目录存在
mkdir -p "${PROFILE_HOME}/memories"

echo ""
echo "==> 安装完成！"
echo ""
echo "    快速开始："
echo "      ${PROFILE_NAME} chat          # 开始与健康管家对话"
echo "      ${PROFILE_NAME} setup         # 配置 API Key 和模型"
echo ""
echo "    首次对话时，健康管家会引导你建立健康档案。"
echo "    档案保存在：${PROFILE_HOME}/memories/health_profile.json"
