"""
=============================================================================
商品 Agent 客户端 — v2.1 ReAct 循环
=============================================================================
接收主路由分发的商品查询子任务，通过 ReAct 循环自主决策：
  - 分析用户意图，决定调用哪个 MCP 工具及参数
  - 观察工具返回结果，判断是否需要调整参数重试
  - 信息充分后自动生成自然语言推荐

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
from config import MCP_PRODUCT_SERVER

setup_logger()

# 商品 Agent 可用工具定义
PRODUCT_TOOLS = [
    {
        "name": "query_product",
        "description": (
            "搜索商品，支持按分类、关键词、品牌、价格区间、最低评分、排序方式等维度组合筛选。"
            "适用场景：搜索特定商品名称（如蓝牙耳机）、按分类浏览（如运动装备）、比价推荐、"
            "按品牌筛选（如小米的产品）、按评分/销量排序。"
            "如果初次查询结果太少或为空，尝试放宽条件（去掉品牌、扩大价格范围、替换关键词）。"
        ),
        "parameters": {
            "category": "商品分类（可选）: electronics(数码电子)/clothing(服饰鞋包)/food(食品饮料)/beauty(美妆个护)/home(家居生活)/sports(运动户外)",
            "keyword": "搜索关键词，模糊匹配商品名称（可选，但大多数查询都应提供）",
            "brand": "品牌名称，模糊匹配（可选）",
            "min_price": "最低价格（可选，单位：元）",
            "max_price": "最高价格（可选，单位：元）",
            "min_rating": "最低评分 1.0-5.0（可选）",
            "sort_by": "排序方式: rating(评分,默认)/sales_count(销量)/price(价格升序)/price_desc(价格降序)",
            "limit": "返回记录数上限，默认20",
        },
    },
]


class ProductAgent:
    """
    商品领域 Agent（ReAct 版本）。
    通过 ReAct 循环自主决定工具调用和参数调整，无需硬编码流程。
    """

    def __init__(self):
        self.mcp_client = MCPClient(MCP_PRODUCT_SERVER["url"])
        self.react_engine = ReActEngine(
            agent_type="商品搜索与推荐",
            tool_definitions=PRODUCT_TOOLS,
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
        处理商品查询子任务（异步，ReAct 循环）。

        Args:
            user_query: 用户查询文本（已经过主路由分解的单一商品子任务）
            trace_id:   全链路追踪 ID
            context:    对话上下文（预留）

        Returns:
            A2A 标准响应格式:
            {
                "task_id": "...",
                "task_type": "product",
                "status": "success" | "error",
                "data": [...],
                "summary": "...",
                "error": null | "错误信息"
            }
        """
        task_id = str(uuid.uuid4())[:8]
        logger.info("[{}] ProductAgent(ReAct) 开始 | task_id={} | query={}",
                    trace_id, task_id, user_query[:100])

        try:
            final_answer = await self.react_engine.run(
                user_query=user_query,
                trace_id=trace_id,
            )

            logger.info("[{}] ProductAgent(ReAct) 完成 | task_id={} | answer_len={}",
                        trace_id, task_id, len(final_answer))

            return {
                "task_id": task_id,
                "task_type": "product",
                "status": "success",
                "data": [],           # ReAct 回答已包含完整自然语言，不再传原始数据
                "total": 0,
                "summary": final_answer,
                "params_used": {},
                "error": None,
            }

        except Exception as e:
            logger.error("[{}] ProductAgent(ReAct) 失败 | task_id={} | {}",
                         trace_id, task_id, str(e))
            return {
                "task_id": task_id,
                "task_type": "product",
                "status": "error",
                "data": [],
                "total": 0,
                "summary": "",
                "params_used": {},
                "error": f"商品查询失败: {e}",
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
        agent = ProductAgent()
        result = await agent.process(
            user_query="我想买个蓝牙耳机，预算500以内，要评分高的",
            trace_id="test-003",
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        await agent.close()

    asyncio.run(main())
