import asyncio
import sys
import os
import hashlib
import json
from pathlib import Path

sys.path.insert(0, "/app/agent")
import mcp_server

# 只允许只读与安全查询工具，彻底禁用写操作、实盘下单与终端执行
ALLOW = set([
    'list_skills', 'load_skill', 'trading_connections', 'trading_check',
    'trading_account', 'trading_positions', 'trading_orders', 'trading_quote',
    'trading_history', 'get_market_data', 'backtest', 'factor_analysis',
    'pattern_recognition', 'technical_indicators', 'get_fundamentals',
    'get_stock_news', 'get_sec_filings', 'get_financial_statements',
    'get_stock_profile', 'search_symbol', 'get_macro_series', 'sentiment',
    'orderbook_depth', 'list_strategies', 'query_strategies',
    'get_strategy_evidence', 'read_run_artifact', 'list_swarm_presets',
    'get_swarm_status', 'get_run_result'
])

mcp_server._include_shell_tools = False
mcp_server._get_registry()

async def restrict():
    for tool in await mcp_server.mcp.list_tools():
        if tool.name not in ALLOW:
            mcp_server.mcp.local_provider.remove_tool(tool.name)

asyncio.run(restrict())

# 容器内无法降低策略执行权限: 对回测代码执行严格哈希指纹校验与防穿越白名单 (Fail-Closed 闭环保护)
# 清单文件由环境变量 APPROVED_RUNS_FILE 或 $VIBE_TRADING_HOME/approved_runs.json 指定
DEFAULT_HOME = Path(os.environ.get("VIBE_TRADING_HOME", Path.home() / ".vibe-trading"))
MANIFEST_FILE = Path(os.environ.get("APPROVED_RUNS_FILE", DEFAULT_HOME / "approved_runs.json")).resolve()

mcp_server.mcp.local_provider.remove_tool("backtest")

@mcp_server.mcp.tool(name="backtest")
def reviewed_backtest(run_dir: str) -> str:
    """Run only an explicitly audited strategy simulation with verified SHA-256 fingerprints."""
    if not MANIFEST_FILE.is_file():
        return json.dumps({
            "status": "error",
            "error": "Security check failed: approved_runs.json manifest not found. Backtest execution rejected."
        })

    try:
        with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
            approved_runs = json.load(f)
    except Exception as e:
        return json.dumps({
            "status": "error",
            "error": f"Failed to load approved runs manifest: {str(e)}"
        })

    if not isinstance(approved_runs, dict):
        return json.dumps({
            "status": "error",
            "error": "Approved runs manifest format error: root must be a JSON object mapping directory paths."
        })

    run = Path(run_dir).resolve()
    manifest = approved_runs.get(str(run))
    if manifest is None:
        return json.dumps({
            "status": "error",
            "error": "Strategy directory is not registered in approved runs manifest."
        })

    if not isinstance(manifest, dict) or len(manifest) == 0:
        return json.dumps({
            "status": "error",
            "error": "Security check failed: strategy manifest must contain a non-empty mapping of files and SHA-256 fingerprints."
        })

    # 递归收集 run 目录下的所有文件，确保没有任何清单外的未审核文件 (防隐藏代码注入)
    actual_files: dict[str, str] = {}
    for p in run.rglob("*"):
        if p.is_file():
            if "__pycache__" in p.parts or p.name.startswith("."):
                continue
            rel = str(p.relative_to(run))
            actual_files[rel] = hashlib.sha256(p.read_bytes()).hexdigest()

    unreviewed = set(actual_files.keys()) - set(manifest.keys())
    if unreviewed:
        return json.dumps({
            "status": "error",
            "error": f"Security violation: unreviewed files found in strategy directory: {sorted(unreviewed)}"
        })

    # 逐文件校验 SHA-256 指纹，确保未经审核的代码绝不执行
    for relative, expected in manifest.items():
        if relative not in actual_files:
            return json.dumps({
                "status": "error",
                "error": f"Required strategy file missing or outside target directory: {relative}"
            })
        if actual_files[relative] != expected:
            return json.dumps({
                "status": "error",
                "error": f"Code integrity violation: SHA-256 fingerprint mismatch for {relative}"
            })

    return mcp_server.backtest(str(run))

if __name__ == "__main__":
    mcp_server.mcp.run(show_banner=False)
