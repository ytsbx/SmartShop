#!/bin/bash
# ============================================================================
# SmartShop v2.0 — 一键启动脚本 (Linux / macOS / Git Bash)
# LangGraph + MCP SDK + SSE 流式输出
# ============================================================================
set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo -e "${CYAN}============================================================${NC}"
echo -e "${CYAN}   SmartShop v2.0 — 一键启动${NC}"
echo -e "${CYAN}   LangGraph + MCP SDK + SSE 流式输出${NC}"
echo -e "${CYAN}============================================================${NC}"
echo ""

# ---- 检查 MySQL ----
echo -e "${YELLOW}[检查]${NC} MySQL 服务..."
if command -v mysqladmin &> /dev/null; then
    if mysqladmin ping -h 127.0.0.1 --silent 2>/dev/null; then
        echo -e "${GREEN}[ OK ]${NC} MySQL 连接正常"
    else
        echo -e "${RED}[警告]${NC} MySQL 未响应，请先启动 MySQL 8.0"
        exit 1
    fi
else
    echo -e "${YELLOW}[跳过]${NC} mysqladmin 未安装，跳过 MySQL 检查"
fi
echo ""

# ---- 检查 Python ----
echo -e "${YELLOW}[检查]${NC} Python 环境..."
python3 --version &>/dev/null || python --version &>/dev/null
echo -e "${GREEN}[ OK ]${NC} Python 可用"
echo ""

# ---- 检查依赖 ----
echo -e "${YELLOW}[检查]${NC} 依赖包..."
pip show langgraph &>/dev/null || {
    echo -e "${YELLOW}[提示]${NC} 正在安装依赖..."
    pip install -r requirements.txt -q
}
echo -e "${GREEN}[ OK ]${NC} 依赖就绪"
echo ""

# ---- 清理旧进程（可选）----
echo -e "${YELLOW}[清理]${NC} 检查端口占用..."
for port in 8100 8101 8008; do
    if lsof -i :$port -t &>/dev/null 2>&1; then
        echo "  端口 $port 被占用，尝试释放..."
        lsof -i :$port -t | xargs kill -9 2>/dev/null || true
    fi
done
echo -e "${GREEN}[ OK ]${NC} 端口检查完成"
echo ""

# ---- 创建日志目录 ----
mkdir -p logs

# ---- 启动服务 ----
echo -e "${CYAN}============================================================${NC}"
echo -e "${CYAN}   启动 MCP 工具服务层${NC}"
echo -e "${CYAN}============================================================${NC}"

echo -e "${YELLOW}[启动]${NC} 商品 MCP Server (端口 8100)..."
python -m uvicorn mcp_servers.mcp_product_server:app --host 127.0.0.1 --port 8100 \
    > logs/product_mcp.log 2>&1 &
echo "  PID: $!"

echo -e "${YELLOW}[启动]${NC} 订单 MCP Server (端口 8101)..."
python -m uvicorn mcp_servers.mcp_order_server:app --host 127.0.0.1 --port 8101 \
    > logs/order_mcp.log 2>&1 &
echo "  PID: $!"

sleep 3

echo -e "${CYAN}============================================================${NC}"
echo -e "${CYAN}   启动 A2A 编排层${NC}"
echo -e "${CYAN}============================================================${NC}"

echo -e "${YELLOW}[启动]${NC} A2A Router Server (端口 8008)..."
python -m uvicorn core.router_A2Aagent_Server:app --host 127.0.0.1 --port 8008 \
    > logs/router.log 2>&1 &
ROUTER_PID=$!
echo "  PID: $ROUTER_PID"

sleep 3

echo -e "${CYAN}============================================================${NC}"
echo -e "${CYAN}   启动交互层${NC}"
echo -e "${CYAN}============================================================${NC}"

echo -e "${YELLOW}[启动]${NC} Streamlit 前端 (端口 8502)..."
streamlit run main.py --server.port 8502 \
    > logs/streamlit.log 2>&1 &
ST_PID=$!
echo "  PID: $ST_PID"

sleep 5

echo ""
echo -e "${GREEN}============================================================${NC}"
echo -e "${GREEN}   SmartShop v2.0 全部服务已启动!${NC}"
echo -e "${GREEN}============================================================${NC}"
echo ""
echo -e "  前端界面:  ${CYAN}http://localhost:8502${NC}"
echo -e "  API 文档:  ${CYAN}http://localhost:8008/docs${NC}"
echo -e "  健康检查:  ${CYAN}http://localhost:8008/api/health${NC}"
echo -e "  SSE 端点:  ${CYAN}http://localhost:8008/api/chat/stream?query=推荐蓝牙耳机${NC}"
echo ""
echo -e "  各服务 PID:"
echo -e "    Router:     $ROUTER_PID"
echo -e "    Streamlit:  $ST_PID"
echo ""
echo -e "  ${YELLOW}关闭所有服务:  ./stop.sh${NC}"
echo -e "${GREEN}============================================================${NC}"
