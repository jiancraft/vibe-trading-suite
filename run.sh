#!/usr/bin/env bash
# ============================================================================
# Vibe-Trading Suite 一键多模启动器
# ============================================================================
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
    echo "使用方式: $0 [选项]"
    echo ""
    echo "选项:"
    echo "  --web      启动单机可视化交易软件 (Docker Web 控制台: http://localhost:8899)"
    echo "  --skill    装载智能体量化技能到本地 (~/.agents/skills/)"
    echo "  --doctor   运行本地多市场行情与量化诊断 (例如: $0 --doctor 600519)"
    echo "  --all      同时启动 Web 操盘台并装载智能体技能"
    echo "  --help     显示帮助信息"
    echo ""
    exit 1
}

if [ "$#" -eq 0 ]; then
    usage
fi

ensure_env() {
    if [ ! -f "$DIR/.env" ]; then
        if [ -f "$DIR/.env.example" ]; then
            echo "⚠️ 未检测到 .env 配置文件，正在从 .env.example 自动生成..."
            cp "$DIR/.env.example" "$DIR/.env"
            RAND_KEY=$(openssl rand -hex 24 2>/dev/null || LC_ALL=C tr -dc 'a-zA-Z0-9' < /dev/urandom | head -c 48)
            sed -i.bak "s/your_custom_api_auth_key_here/$RAND_KEY/" "$DIR/.env" && rm -f "$DIR/.env.bak"
            echo "🔐 已为您自动生成本地安全口令 API_AUTH_KEY"
        fi
    else
        # 若用户手动复制模板但未修改占位符，自动升级为安全随机口令
        if grep -q "your_custom_api_auth_key_here" "$DIR/.env"; then
            echo "⚠️ 检测到 .env 中包含默认占位口令，正在自动替换为高强度随机密钥..."
            RAND_KEY=$(openssl rand -hex 24 2>/dev/null || LC_ALL=C tr -dc 'a-zA-Z0-9' < /dev/urandom | head -c 48)
            sed -i.bak "s/your_custom_api_auth_key_here/$RAND_KEY/" "$DIR/.env" && rm -f "$DIR/.env.bak"
            echo "🔐 已自动升级为安全口令 API_AUTH_KEY"
        fi
    fi
}

case "$1" in
    --web)
        ensure_env
        echo "🚀 正在启动单机可视化交易软件 (Docker)..."
        docker compose up -d
        echo "✅ 启动成功！请打开浏览器访问: http://localhost:8899"
        ;;
    --skill)
        echo "🤖 正在装载 trading-expert-ops Skill 到当前用户技能目录..."
        TARGET_DIR="$HOME/.agents/skills"
        mkdir -p "$TARGET_DIR"
        ln -snf "$DIR/skills/trading-expert-ops" "$TARGET_DIR/trading-expert-ops"
        echo "✅ 挂载成功！已软链接到: $TARGET_DIR/trading-expert-ops"
        echo "💡 现在可在 Antigravity / Claude Code / Codex 中直接使用量化交易专家能力！"
        ;;
    --doctor)
        shift
        python3 "$DIR/scripts/stock_doctor.py" "$@"
        ;;
    --all)
        ensure_env
        echo "🚀 正在启动双模合体模式 (Web + Skill)..."
        docker compose up -d
        TARGET_DIR="$HOME/.agents/skills"
        mkdir -p "$TARGET_DIR"
        ln -snf "$DIR/skills/trading-expert-ops" "$TARGET_DIR/trading-expert-ops"
        echo "✅ 全部启动就绪！Web 看板: http://localhost:8899 | 智能体技能已加载"
        ;;
    --help|-h)
        usage
        ;;
    *)
        echo "未知选项: $1"
        usage
        ;;
esac
