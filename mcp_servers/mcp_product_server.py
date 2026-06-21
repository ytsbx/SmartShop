"""
=============================================================================
商品 MCP 服务端
=============================================================================
基于 FastMCP + SSE 传输，遵循官方 MCP 协议。
提供商品搜索、筛选、比价等查询能力。

启动方式:
    python -m uvicorn mcp_servers.mcp_product_server:app --host 127.0.0.1 --port 8100
=============================================================================
"""

import sys
import os
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
mcp = FastMCP("SmartShop Product MCP Server")

# ============================================================================
# FastAPI 应用（用于 /health 和 SSE mount）
# ============================================================================
app = FastAPI(
    title="SmartShop Product MCP Server",
    version="2.0.0",
    description="商品领域 MCP 服务端 — FastMCP + SSE 传输",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# 核心业务逻辑：商品 SQL 构建
# ============================================================================
def build_product_query(params: dict) -> tuple:
    """
    根据查询参数构建参数化 SQL。

    支持多维筛选：分类、关键词、品牌、价格区间、最低评分、排序方式。
    """
    conditions = ["1=1"]
    query_params = []

    category = params.get("category")
    keyword = params.get("keyword")
    brand = params.get("brand")
    min_price = params.get("min_price")
    max_price = params.get("max_price")
    min_rating = params.get("min_rating")
    sort_by = params.get("sort_by", "rating")
    limit = min(params.get("limit", 20), SQL_SAFE_CONFIG["max_return_rows"])

    # 分类筛选
    if category and category != "all":
        conditions.append("category = %s")
        query_params.append(category)

    # 关键词搜索（模糊匹配 name 或 keywords）
    if keyword:
        conditions.append("(name LIKE %s OR keywords LIKE %s)")
        kw_pattern = f"%{keyword}%"
        query_params.append(kw_pattern)
        query_params.append(kw_pattern)

    # 品牌筛选
    if brand:
        conditions.append("brand LIKE %s")
        query_params.append(f"%{brand}%")

    # 价格区间
    if min_price is not None:
        conditions.append("price >= %s")
        query_params.append(float(min_price))
    if max_price is not None:
        conditions.append("price <= %s")
        query_params.append(float(max_price))

    # 最低评分
    if min_rating is not None:
        conditions.append("rating >= %s")
        query_params.append(float(min_rating))

    # 排序
    sort_map = {
        "price": "price ASC",
        "price_desc": "price DESC",
        "sales_count": "sales_count DESC",
        "rating": "rating DESC",
        "stock": "stock DESC",
    }
    order_clause = sort_map.get(sort_by, "rating DESC, sales_count DESC")

    where_clause = " AND ".join(conditions)
    sql = (
        "SELECT id, name, category, brand, price, original_price, stock, "
        "       rating, sales_count, description, store_name, specs "
        "FROM product_info "
        f"WHERE {where_clause} "
        f"ORDER BY {order_clause} "
        f"LIMIT {limit}"
    )

    return sql, tuple(query_params)


# ============================================================================
# MCP 工具注册
# ============================================================================
@mcp.tool()
def ping() -> dict:
    """健康检查"""
    return {"status": "ok", "service": "product_mcp"}


@mcp.tool()
def query_product(
    category: Optional[str] = None,
    keyword: Optional[str] = None,
    brand: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    min_rating: Optional[float] = None,
    sort_by: str = "rating",
    limit: int = 20,
    trace_id: str = "unknown",
) -> dict:
    """
    搜索商品，支持按分类、关键词、品牌、价格、评分等多维筛选。

    适用场景：
    - "蓝牙耳机" → keyword="蓝牙耳机"
    - "500以内的机械键盘" → keyword="机械键盘", max_price=500
    - "评分最高的手机" → category="electronics", keyword="手机", sort_by="rating"
    - "小米的产品" → brand="小米"

    Args:
        category: 商品分类 — electronics/clothing/food/beauty/home/sports/all（可选）
        keyword: 搜索关键词，模糊匹配商品名称和关键词字段（可选）
        brand: 品牌名称，模糊匹配（可选）
        min_price: 最低价格筛选（可选）
        max_price: 最高价格筛选（可选）
        min_rating: 最低评分筛选 1.0-5.0（可选）
        sort_by: 排序方式 — rating(评分)/sales_count(销量)/price(价格升序)/price_desc(价格降序)
        limit: 返回记录数上限，默认 20
        trace_id: 追踪 ID
    """
    logger.info("[{}] query_product | category={} | keyword={} | brand={} | "
                "price={}-{} | rating>={} | sort={}",
                trace_id, category, keyword, brand, min_price, max_price, min_rating, sort_by)

    params = {
        "category": category,
        "keyword": keyword,
        "brand": brand,
        "min_price": min_price,
        "max_price": max_price,
        "min_rating": min_rating,
        "sort_by": sort_by,
        "limit": limit,
    }

    sql, sql_params = build_product_query(params)
    rows = execute_query(sql, sql_params, trace_id=trace_id)

    logger.info("[{}] query_product 完成 | rows={}", trace_id, len(rows))
    return {"total": len(rows), "data": rows}


# ============================================================================
# FastAPI 路由
# ============================================================================
@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "product_mcp_server"}


# ============================================================================
# 挂载 MCP SSE 应用到 FastAPI
# ============================================================================
app.mount("/mcp", mcp.sse_app())


# ============================================================================
# 直接启动入口
# ============================================================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8100, log_level="info")
