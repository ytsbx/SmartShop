"""
=============================================================================
订单 Agent 客户端 — v2.1 ReAct 循环
=============================================================================
接收主路由分发的订单查询子任务，通过 ReAct 循环自主决策：
  - 分析用户意图，决定调用哪个 MCP 工具及参数
  - 观察工具返回结果，判断是否需要调整参数重试
  - 信息充分后自动生成自然语言订单摘要

遵循 A2A 统一消息规范。
v2.0: 迁移到官方 MCP SDK + Prompt 外置
v2.1: 用 ReActEngine 替代固定三段式（参数提取→调用→摘要），Agent 自主决策
=============================================================================
"""

import sys
import os
import json
import uuid
from typing import Optional, Dict, Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from loguru import logger

from core.mcp_client import MCPClient
from core.react_loop import ReActEngine
from core.logger import setup_logger
from config import MCP_ORDER_SERVER

setup_logger()

# 订单 Agent 可用工具定义
ORDER_TOOLS = [
    {
        "name": "query_order",
        "description": (
            "查询订单信息，支持按订单号、客户姓名、订单状态、日期范围等维度组合筛选。"
            "适用场景：查询某人的所有订单、按状态筛选（待支付/已发货/运输中/已签收/已完成/已退款）、"
            "按时间范围筛选（最近一周/一个月）、按订单号精确查询、按商品关键词模糊匹配。"
            "如果初次查询结果太少或为空，尝试放宽条件（扩大日期范围、去掉状态限制）。"
            "注意：'运输中'对应 status='shipped'，'到哪了'/'物流'/'快递'也对应 status='shipped'。"
        ),
        "parameters": {
            "order_no": "订单编号，精确匹配（可选，如 ORD20260619001）",
            "customer_name": "客户姓名，模糊匹配（可选，如'张三'。用户说'我的''我'且未提供姓名时留空）",
            "status": "订单状态（可选）: pending(待支付)/paid(已支付)/shipped(运输中)/delivered(已签收)/completed(已完成)/refunded(已退款)",
            "order_date_from": "下单起始日期 YYYY-MM-DD（可选，如'最近一周'应计算为7天前）",
            "order_date_to": "下单截止日期 YYYY-MM-DD（可选）",
            "limit": "返回记录数上限，默认20",
        },
    },
]


class OrderAgent:
    """
    订单领域 Agent（ReAct 版本）。
    通过 ReAct 循环自主决定工具调用和参数调整，无需硬编码流程。
    """

    def __init__(self):
        self.mcp_client = MCPClient(MCP_ORDER_SERVER["url"])
        self.react_engine = ReActEngine(
            agent_type="订单查询与追踪",
            tool_definitions=ORDER_TOOLS,
            tool_executor=self._execute_tool,
        )

    async def _execute_tool(
        self, tool_name: str, arguments: Dict[str, Any], trace_id: str
    ) -> Dict[str, Any]:
        """
        ReAct 工具回调：过滤 None 参数后通过 MCP 客户端执行。
        """
        # 过滤 None 值，避免 MCP Server 参数校验报错
        filtered = {k: v for k, v in arguments.items() if v is not None}
        return await self.mcp_client.call_tool(
            tool_name=tool_name,
            arguments=filtered,
            trace_id=trace_id,
        )

    async def process(
        self,
        user_query: str,
        trace_id: str = "unknown",
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        处理订单查询子任务（异步，ReAct 循环）。

        Args:
            user_query: 用户查询文本（已经过主路由分解的单一订单子任务）
            trace_id:   全链路追踪 ID
            context:    对话上下文（预留）

        Returns:
            A2A 标准响应格式:
            {
                "task_id": "...",
                "task_type": "order",
                "status": "success" | "error",
                "data": [...],
                "summary": "...",
                "error": null | "错误信息"
            }
        """
        task_id = str(uuid.uuid4())[:8]
        logger.info("[{}] OrderAgent(ReAct) 开始 | task_id={} | query={}",
                    trace_id, task_id, user_query[:100])

        try:
            final_answer = await self.react_engine.run(
                user_query=user_query,
                trace_id=trace_id,
            )

            logger.info("[{}] OrderAgent(ReAct) 完成 | task_id={} | answer_len={}",
                        trace_id, task_id, len(final_answer))

            return {
                "task_id": task_id,
                "task_type": "order",
                "status": "success",
                "data": [],           # ReAct 回答已包含完整自然语言
                "total": 0,
                "summary": final_answer,
                "params_used": {},
                "error": None,
            }

        except Exception as e:
            logger.error("[{}] OrderAgent(ReAct) 失败 | task_id={} | {}",
                         trace_id, task_id, str(e))
            return {
                "task_id": task_id,
                "task_type": "order",
                "status": "error",
                "data": [],
                "total": 0,
                "summary": "",
                "params_used": {},
                "error": f"订单查询失败: {e}",
            }

    async def close(self):
        """释放资源"""
        await self.mcp_client.close()


# ============================================================================
# 独立运行模式（用于调试）
# ============================================================================
if __name__ == "__main__":
    import asyncio

    async def main():
        agent = OrderAgent()
        result = await agent.process(
            user_query="帮我查下张三最近一周的订单",
            trace_id="test-004",
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        await agent.close()

    asyncio.run(main())
