"""
=============================================================================
订单 MCP 服务端
=============================================================================
基于 FastMCP + SSE 传输，遵循官方 MCP 协议。
提供订单查询、状态追踪、物流查询等能力。

启动方式:
    python -m uvicorn mcp_servers.mcp_order_server:app --host 127.0.0.1 --port 8101
=============================================================================
"""

import sys
import os
import re
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from mcp.server.fastmcp import FastMCP
from loguru import logger

from data.mysql_conn import execute_query
from config import SQL_SAFE_CONFIG
from core.logger import setup_logger

setup_logger()

# ============================================================================
# FastMCP 实例
# ============================================================================
mcp = FastMCP("SmartShop Order MCP Server")

# ============================================================================
# FastAPI 应用（用于 /health 和 SSE mount）
# ============================================================================
app = FastAPI(
    title="SmartShop Order MCP Server",
    version="2.0.0",
    description="订单领域 MCP 服务端 — FastMCP + SSE 传输",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# 核心业务逻辑：订单 SQL 构建
# ============================================================================
def _validate_date(date_str: Optional[str]) -> Optional[str]:
    """校验日期格式 YYYY-MM-DD"""
    if date_str is None:
        return None
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
        raise ValueError("日期格式必须为 YYYY-MM-DD")
    return date_str


def build_order_query(params: dict) -> tuple:
    """
    根据查询参数构建参数化 SQL。

    支持按订单号、客户、状态、日期范围筛选。
    """
    conditions = ["1=1"]
    query_params = []

    order_no = params.get("order_no")
    customer_name = params.get("customer_name")
    status = params.get("status")
    order_date_from = params.get("order_date_from")
    order_date_to = params.get("order_date_to")
    limit = min(params.get("limit", 20), SQL_SAFE_CONFIG["max_return_rows"])

    # 订单号精确匹配
    if order_no:
        conditions.append("order_no = %s")
        query_params.append(order_no)

    # 客户名模糊匹配
    if customer_name:
        conditions.append("customer_name LIKE %s")
        query_params.append(f"%{customer_name}%")

    # 订单状态
    if status and status != "all":
        valid_statuses = ["pending", "paid", "shipped", "delivered", "completed", "refunded"]
        if status not in valid_statuses:
            raise ValueError(f"status 必须为 {'/'.join(valid_statuses)} 之一，当前值: {status}")
        conditions.append("status = %s")
        query_params.append(status)

    # 日期范围
    if order_date_from:
        _validate_date(order_date_from)
        conditions.append("order_date >= %s")
        query_params.append(order_date_from)
    if order_date_to:
        _validate_date(order_date_to)
        conditions.append("order_date <= %s")
        query_params.append(order_date_to)

    where_clause = " AND ".join(conditions)
    sql = (
        "SELECT id, order_no, product_name, category, customer_name, quantity, "
        "       unit_price, total_price, status, logistics_company, tracking_no, "
        "       order_date, delivery_address, phone, customer_note "
        "FROM order_info "
        f"WHERE {where_clause} "
        "ORDER BY order_date DESC, id DESC "
        f"LIMIT {limit}"
    )

    return sql, tuple(query_params)


# ============================================================================
# MCP 工具注册
# ============================================================================
@mcp.tool()
def ping() -> dict:
    """健康检查"""
    return {"status": "ok", "service": "order_mcp"}


@mcp.tool()
def query_order(
    order_no: Optional[str] = None,
    customer_name: Optional[str] = None,
    status: Optional[str] = None,
    order_date_from: Optional[str] = None,
    order_date_to: Optional[str] = None,
    limit: int = 20,
    trace_id: str = "unknown",
) -> dict:
    """
    查询订单信息，支持按订单号、客户、状态、日期范围筛选。

    适用场景：
    - "查我的订单" → customer_name="张三"
    - "我的订单到哪了" → customer_name="张三", status="shipped"
    - "最近一周的订单" → order_date_from="2026-06-12", order_date_to="2026-06-19"
    - "已完成的订单" → customer_name="张三", status="completed"

    Args:
        order_no: 订单编号，精确匹配（可选）
        customer_name: 客户姓名，模糊匹配（可选）
        status: 订单状态 — pending/paid/shipped/delivered/completed/refunded/all（可选）
        order_date_from: 下单起始日期 YYYY-MM-DD（可选）
        order_date_to: 下单截止日期 YYYY-MM-DD（可选）
        limit: 返回记录数上限，默认 20
        trace_id: 追踪 ID
    """
    logger.info("[{}] query_order | order_no={} | customer={} | status={} | date={}~{}",
                trace_id, order_no, customer_name, status, order_date_from, order_date_to)

    params = {
        "order_no": order_no,
        "customer_name": customer_name,
        "status": status,
        "order_date_from": order_date_from,
        "order_date_to": order_date_to,
        "limit": limit,
    }

    sql, sql_params = build_order_query(params)
    rows = execute_query(sql, sql_params, trace_id=trace_id)

    logger.info("[{}] query_order 完成 | rows={}", trace_id, len(rows))
    return {"total": len(rows), "data": rows}


# ============================================================================
# FastAPI 路由
# ============================================================================
@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "order_mcp_server"}


# ============================================================================
# 挂载 MCP SSE 应用到 FastAPI
# ============================================================================
app.mount("/mcp", mcp.sse_app())


# ============================================================================
# 直接启动入口
# ============================================================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8101, log_level="info")
