"""
=============================================================================
LangGraph 图组装与编译
=============================================================================
构建 SmartShop 编排图，包含:
- 澄清门 → 查询分解 → 条件路由 → 并行 Agent 分发 → 结果聚合
- 通过 AsyncSqliteSaver 支持 checkpoint 持久化

图结构 (v2.1):
    START → clarify_query ─┬─ needs_clarification → aggregate → END
                            │
                            └─ clear ─→ decompose_query ─┬─ (无子查询) → aggregate → END
                                                          │
                                                          └─ (有子查询) → Send(product_agent) × N
                                                                         → Send(order_agent) × M
                                                                                │
                                                                  ┌─────────────┴──────────────┐
                                                                  ▼                            ▼
                                                            product_agent                 order_agent
                                                                  │                            │
                                                                  └──────────┬─────────────────┘
                                                                             ▼
                                                                        aggregate → END
=============================================================================
"""

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from core.state import MainState
from core.graph_nodes import (
    clarify_query_node,
    route_after_clarify,
    decompose_query_node,
    route_after_decompose,
    product_agent_node,
    order_agent_node,
    aggregate_node,
)


def build_graph(checkpointer: AsyncSqliteSaver):
    """
    构建并编译 LangGraph 编排图。

    关键：route_after_decompose 直接根据 type 发送 Send 到对应 Agent，
    不再经过中间 agent_router 节点（避免了 Send arg 在节点间丢失的问题）。
    """
    builder = StateGraph(MainState)

    # ---- 注册节点 ----
    builder.add_node("clarify_query", clarify_query_node)
    builder.add_node("decompose_query", decompose_query_node)
    builder.add_node("product_agent", product_agent_node)
    builder.add_node("order_agent", order_agent_node)
    builder.add_node("aggregate", aggregate_node)

    # ---- 连线 ----
    builder.add_edge(START, "clarify_query")

    # 条件边: clarify → decompose（清晰查询）或 aggregate（生成追问）
    builder.add_conditional_edges("clarify_query", route_after_clarify)

    # 条件边: decompose → 直接 Send 到对应 Agent，或 aggregate
    builder.add_conditional_edges(
        "decompose_query",
        route_after_decompose,
    )

    # Agent 节点都汇聚到 aggregate
    builder.add_edge("product_agent", "aggregate")
    builder.add_edge("order_agent", "aggregate")

    # 最终输出
    builder.add_edge("aggregate", END)

    # ---- 编译（带 checkpoint）----
    return builder.compile(checkpointer=checkpointer)
