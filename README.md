# Vibe-Trading Suite: 个人多市场量化交易系统与智能体工作站

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Docker](https://img.shields.io/badge/Docker-Enabled-blue.svg)](docker-compose.yml)
[![Standard](https://img.shields.io/badge/Protocol-DS--A--STOCK--STD--1.0-brightgreen.svg)](skills/trading-expert-ops/references/ds_a_stock_std_1.0.md)

> 一套融合**单机可视化交易看盘软件 (React/Web)** 与 **AI 智能体大脑 (Standard Agent Skill)** 的全栈多市场量化交易解决方案。
> 
> ℹ️ **开源与上游致谢**：本项目基于 [HKUDS/Vibe-Trading](https://github.com/HKUDS/Vibe-Trading)（MIT 许可）架构深度开发与扩展，集成了 A股/美港股/加密货币多市场量化因子、OKX 逐仓实盘风控与标准化 AI 智能体技能。详情参见 [NOTICE](NOTICE)。

---

## 🌟 系统核心架构与两大策略体系

1. **套 A（A股短线游资量价模型 · DS-A-STOCK-STD-1.0）**：
   * 盯量价 + 形态 + 游资点火动量（国泰君安 191 因子、SMC 机构订单块、缠论笔中枢分解）；
   * 严格执行 6 选 1 唯一明确操作标签，三色大盘闸门，浮亏绝对禁止加仓。
2. **套 B（加密合约全天候实盘模型 · Suite-B-v2.0）**：
   * 盯资金费率 + 盘口深度 (L2) + 爆流清算区；
   * 强制逐仓隔离（isolated）、显式锁死杠杆、盘口价差保护锁、三阶动态出场（40%/30%/30% 止盈推保本与 Trailing 追踪）。
3. **美港股核心持仓动量与风控**：
   * 组合相关性矩阵防假分散（>0.80 预警）、动态 8% 移动止损线自动追踪。

---

## 🚀 极速上手：两种使用模式

本项目支持**本地极客工作站**与**云端无人值守实盘**两种部署形态：

### 模式一：本地单机部署模式 (Local Workstation)
适合日内盯盘、复盘分析、股票诊断与策略回测，零服务器成本，隐私 100% 留在本地。

```bash
# 1. 克隆代码仓库
git clone https://github.com/jiancraft/vibe-trading-suite.git
cd vibe-trading-suite

# 2. 复制配置模板并填入您的自选标的
cp .env.example .env
cp config/portfolio.example.json config/portfolio.json

# 3. 启动单机可视化交易软件 (Web 控制台)
./run.sh --web
# 浏览器打开: http://localhost:8899

# 4. (可选) 将智能体技能挂载至本地 AI (Claude Code / Codex / Antigravity)
./run.sh --skill
```

### 模式二：云端全天候部署模式 (Cloud 24/7 VPS Daemon)
适合加密合约 7×24 小时高频实盘、防插针保本损推升与 Telegram 手机战报接收。

```bash
# 在您的云服务器 (Ubuntu/Debian) 上执行：
git clone https://github.com/jiancraft/vibe-trading-suite.git /opt/vibe-trading
cd /opt/vibe-trading
cp .env.example .env

# 编辑配置填入您的交易所 API 与 Telegram 机器人 Token
nano .env

# 执行一键云端部署向导
bash deploy-cloud.sh
```

---

## 🤖 智能体使用说明 (Agent Skills)

本仓库提供标准化的 **`trading-expert-ops` Skill**，位于 `skills/trading-expert-ops/`。任何遵循 Agent Skill 规范的智能体均可直接挂载。

挂载后，您可在对话框直接提出操盘需求：
* “诊断一下 600519 (贵州茅台)”
* “分析 BTC-USDT 当前盘口深度与资金费率”
* “检查持仓风险与移动止损安全垫”

智能体将严格遵循 `DS-A-STOCK-STD-1.0` 规范，一次性输出【全景核算看板 + 明确操作标签 + 实战口诀 + 极端风控线】。

---

## 🛡️ 安全与免责声明

1. 本软件为量化研究与交易辅助工具，投资有风险，入市需谨慎；
2. 切勿在任何公共场合泄漏您的 API Key、私钥或服务器登录凭证；
3. 本项目遵循 MIT 开源协议。
