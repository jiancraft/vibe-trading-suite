#!/usr/bin/env bash
# ============================================================================
# Vibe-Trading Suite 云端 VPS 一键无人值守部署脚本 (Headless 24/7)
# ============================================================================
set -e

echo "=== Vibe-Trading Suite 云端部署向导 ==="

# 1. 检查 Docker 环境
if ! command -v docker &> /dev/null; then
    echo "📦 正在安装 Docker..."
    curl -fsSL https://get.docker.com | sh
    systemctl enable --now docker
fi

# 2. 检查 .env 配置文件
if [ ! -f .env ]; then
    if [ -f .env.example ]; then
        echo "⚠️ 未发现 .env 配置文件，正在从 .env.example 创建..."
        cp .env.example .env
        echo "📝 请编辑 .env 文件填入您的 API 密钥与 Telegram Token，然后重新运行本脚本。"
        exit 1
    else
        echo "❌ 缺少配置模板 .env.example"
        exit 1
    fi
fi

# 2.1 检查 API 认证密钥安全门禁 (读取 Compose 实际解析出的值并检查长度与强口令)
KEY="$(docker compose config 2>/dev/null | awk -F': ' '/API_AUTH_KEY:/{gsub(/"/,"",$2);print $2;exit}')"
if [ -z "$KEY" ] || [ "${#KEY}" -lt 24 ] || [[ "$KEY" == your_* ]]; then
    echo "❌ 安全拦截: API_AUTH_KEY 缺失、为占位符或少于 24 位，拒绝公网部署！"
    echo "   为了防止云端 VPS 控制台端口 (8899) 在公网遭受未授权访问，"
    echo "   请在 .env 中设置至少 24 位的高强度口令作为 API_AUTH_KEY。"
    echo "   可用以下命令快速生成: openssl rand -hex 24"
    exit 1
fi

# 3. 启动云端容器
echo "🚀 正在构建并拉起云端交易容器..."
docker compose up -d --build

# 4. 安装宿主机 Watchdog 自动愈合服务
echo "🛡️ 正在安装宿主机 Watchdog 自愈巡检..."
WATCHDOG_SCRIPT="/usr/local/bin/vibe_watchdog.sh"
cat << 'EOF' > "$WATCHDOG_SCRIPT"
#!/usr/bin/env bash
if ! docker ps | grep -q vibe-trading-app; then
    echo "[$(date)] Vibe-Trading 容器离线，正在自愈重启..." >> /var/log/vibe_watchdog.log
    docker compose -f /opt/vibe-trading/docker-compose.yml up -d
fi
EOF
chmod +x "$WATCHDOG_SCRIPT"

# 注入 crontab 每分钟巡检
(crontab -l 2>/dev/null | grep -v "vibe_watchdog.sh" ; echo "* * * * * $WATCHDOG_SCRIPT >/dev/null 2>&1") | crontab -

ACTUAL_BIND="$(docker compose config 2>/dev/null | awk -F': ' '/host_ip:/{gsub(/"/,"",$2);print $2;exit}')"
echo "=================================================="
echo "✅ 云端无人值守实盘部署完成！"
echo "🌐 监听绑定: ${ACTUAL_BIND:-127.0.0.1}:8899"
if [ "${ACTUAL_BIND}" = "127.0.0.1" ]; then
    echo "💡 提示: 端口当前绑定于 127.0.0.1 (安全模式)，推荐前置 Nginx/Caddy 反向代理并配置 HTTPS。"
    echo "   若需直接公网访问，可在 .env 中设置 BIND_ADDR=0.0.0.0 后执行 docker compose up -d。"
else
    echo "⚠️ 提示: 端口已向公网开放 (${ACTUAL_BIND})，请确保防火墙安全组及 API_AUTH_KEY 强密码已生效。"
fi
echo "守护状态: 每分钟自动巡检自愈已激活"
echo "=================================================="
