#!/usr/bin/env bash
# 屯象OS — Claude Code SessionStart Hook
# 每次新会话启动时自动执行，输出经验教训摘要和待办状态

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
LESSONS="$ROOT/tasks/lessons.md"
TODO="$ROOT/tasks/todo.md"
TODAY=$(date +%Y-%m-%d)
WEEKDAY=$(date +%u)  # 1=Monday, 7=Sunday

echo "═══════════════════════════════════════════════════════"
echo "  屯象OS · 会话初始化  $TODAY"
echo "═══════════════════════════════════════════════════════"
echo ""

# ── 1. 经验教训摘要 ──
if [ -f "$LESSONS" ]; then
    LESSON_COUNT=$(grep -c '^### L[0-9]' "$LESSONS" 2>/dev/null || echo "0")
    LATEST_LESSONS=$(grep '^### L[0-9]' "$LESSONS" | tail -5 | sed 's/^### /  · /')
    echo "📖 经验教训: 共 ${LESSON_COUNT} 条记录"
    if [ -n "$LATEST_LESSONS" ]; then
        echo "   最近 5 条:"
        echo "$LATEST_LESSONS"
    fi
else
    echo "📖 经验教训: tasks/lessons.md 不存在"
fi
echo ""

# ── 2. 待办任务状态 ──
if [ -f "$TODO" ]; then
    TOTAL=$(grep -c '^\- \[' "$TODO" 2>/dev/null || echo "0")
    DONE=$(grep -c '^\- \[x\]' "$TODO" 2>/dev/null || echo "0")
    PENDING=$((TOTAL - DONE))
    echo "📋 待办任务: ${PENDING} 项未完成 / ${TOTAL} 项总计"
    if [ "$PENDING" -gt 0 ]; then
        echo "   未完成项:"
        grep '^\- \[ \]' "$TODO" | head -5 | sed 's/^/  /'
    fi
else
    echo "📋 待办任务: tasks/todo.md 不存在"
fi
echo ""

# ── 3. Git 分支状态 ──
if command -v git &>/dev/null && git -C "$ROOT" rev-parse --is-inside-work-tree &>/dev/null; then
    BRANCH=$(git -C "$ROOT" branch --show-current 2>/dev/null || echo "unknown")
    UNCOMMITTED=$(git -C "$ROOT" status --porcelain 2>/dev/null | wc -l | tr -d ' ')
    echo "🔀 当前分支: $BRANCH (${UNCOMMITTED} 个未提交变更)"
fi
echo ""

# ── 4. 自检提醒 ──
echo "⚡ 会话协议提醒:"
echo "   1. 先读 tasks/lessons.md 防止重蹈覆辙"
echo "   2. 遵循上下文分级加载协议（Phase 1→5，禁止跳级）"
echo "   3. 非平凡任务先写计划到 tasks/todo.md"
echo "   4. 标记完成前问：一个高级工程师会批准这个吗？"
echo ""
echo "═══════════════════════════════════════════════════════"
