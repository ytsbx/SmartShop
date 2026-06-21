"""
=============================================================================
LangGraph 状态定义
=============================================================================
定义 MainState TypedDict，作为图中所有节点的共享状态结构。

state 字段说明:
- messages:      完整对话历史，由 operator.add reducer 自动追加
- user_query:    当前轮次用户输入文本
- sub_queries:   查询分解后的子查询列表 [{type: str, query: str}]
- sub_results:   Agent 执行结果列表，由 operator.add reducer 自动汇聚
- final_response: 聚合后的最终自然语言回复
- thread_id:     会话标识（用于 checkpoint 恢复）
=============================================================================
"""

from typing import Annotated, TypedDict, Optional, Any
from operator import add


class SubQuery(TypedDict, total=False):
    """单个子查询"""
    type: str         # "product" | "order" | "general"
    query: str        # 完整自然语言子查询


class SubResult(TypedDict, total=False):
    """单个子查询的 Agent 执行结果"""
    task_id: str
    task_type: str               # "product" | "order"
    status: str                  # "success" | "error"
    data: list                   # 原始查询结果行
    total: int                   # 结果行数
    summary: str                 # LLM 生成的自然语言摘要
    params_used: dict            # Agent 提取的参数
    error: Optional[str]         # 错误信息
    _sub_type: str               # 原始子查询类型（元数据）
    _sub_query: str              # 原始子查询文本（元数据）


class MainState(TypedDict):
    """
    LangGraph 主状态。
    所有节点共享此状态，LangGraph checkpoint 按 thread_id 持久化。
    """
    # 对话历史 — 使用 operator.add reducer，新消息自动追加到列表末尾
    messages: Annotated[list[dict[str, str]], add]

    # 当前轮次用户输入
    user_query: str

    # 查询分解结果
    sub_queries: list[SubQuery]

    # Agent 执行结果 — add reducer 自动将并行分支的结果汇聚到一个列表
    sub_results: Annotated[list[SubResult], add]

    # 最终聚合回复
    final_response: str

    # 当前正在处理的子查询（Send fan-out 时由 Send arg 注入）
    sub_query: SubQuery

    # 会话标识（用于 checkpoint）
    thread_id: str

    # v2.1: 澄清门字段
    needs_clarification: bool           # 查询是否需要澄清（过于模糊）
    clarification_question: str         # 澄清追问内容
