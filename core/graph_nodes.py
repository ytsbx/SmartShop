"""
=============================================================================
LangGraph 图节点函数
=============================================================================
包含 SmartShop 编排流程中的全部节点：

0. clarify_query_node — 澄清门：判断查询是否足够具体（v2.1 新增）
0b. route_after_clarify — 澄清后路由：模糊→aggregate / 清晰→decompose
1. decompose_query_node — LLM 将用户查询分解为子查询列表
2. route_after_decompose — 条件边：无子查询 → aggregate / 有子查询 → Send fan-out
3. product_agent_node — 调用商品 Agent 执行子查询
4. order_agent_node — 调用订单 Agent 执行子查询
5. aggregate_node — LLM 汇总所有子结果生成最终回复（v2.1: 支持 token 流式输出 + 澄清问题）

v2.1: aggregate_node 支持通过 config["configurable"]["token_queue"] 实现流式输出
     新增 clarify_query_node 实现模糊查询主动追问
=============================================================================
"""

import json
from datetime import date
from typing import Optional

from loguru import logger

from langgraph.types import Send
from langchain_core.runnables import RunnableConfig

from core.llm_utils import llm_client
from core.prompt_loader import load_prompt
from core.state import MainState, SubQuery


# ============================================================================
# Node 0: 澄清门 — 判断查询是否足够具体
# ============================================================================
async def clarify_query_node(state: MainState) -> dict:
    """
    检查用户查询是否过于模糊。如果太笼统，生成澄清追问，跳过后续分解流程。

    仅用一次轻量 LLM 调用判断意图明确度。
    问候/感谢/道别等社交对话不会被拦截（交给 aggregate 生成友好回复）。
    """
    user_query = state.get("user_query", "")
    messages = state.get("messages", [])
    trace_id = state.get("thread_id", "unknown")

    # 构建对话历史上下文（与 decompose 节点一致）
    if messages:
        lines = []
        for msg in messages[-10:]:
            role = "用户" if msg.get("role") == "user" else "助手"
            content = msg.get("content", "")[:200]
            lines.append(f"{role}: {content}")
        history_text = "\n".join(lines)
    else:
        history_text = "（无历史对话）"

    prompt = load_prompt(
        "clarify",
        today=date.today().isoformat(),
        history=history_text,
        user_query=user_query,
    )

    response = llm_client.chat(
        [{"role": "user", "content": prompt}],
        trace_id=trace_id,
    )
    result = _parse_clarify_json(response)

    needs = result.get("needs_clarification", False)
    question = result.get("clarification_question", "")

    logger.info("[{}] 澄清门判断 | needs_clarification={} | question={}",
                trace_id, needs, question[:80] if question else "N/A")
    return {
        "needs_clarification": needs,
        "clarification_question": question,
    }


def _parse_clarify_json(text: str) -> dict:
    """安全解析 clarify 节点的 JSON 响应。"""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        parsed = json.loads(text)
        return {
            "needs_clarification": parsed.get("needs_clarification", False),
            "clarification_question": parsed.get("clarification_question", ""),
        }
    except json.JSONDecodeError:
        logger.warning("clarify JSON 解析失败: {}", text[:200])
        return {"needs_clarification": False, "clarification_question": ""}


def route_after_clarify(state: MainState):
    """
    澄清后路由：
    - needs_clarification=true  → 跳过分解，直接到 aggregate（生成追问）
    - needs_clarification=false → 正常进入查询分解流程
    """
    if state.get("needs_clarification", False):
        logger.info("[{}] 查询过于模糊 → 生成澄清追问", state.get("thread_id", "unknown"))
        return "aggregate"
    return "decompose_query"


# ============================================================================
# Node 1: 查询分解
# ============================================================================
async def decompose_query_node(state: MainState) -> dict:
    """
    调用 LLM 将用户输入分解为独立的子查询。

    Input:  state.user_query, state.messages
    Output: {sub_queries: [{type, query}, ...]}
    """
    user_query = state.get("user_query", "")
    messages = state.get("messages", [])
    trace_id = state.get("thread_id", "unknown")

    # 构建对话历史上下文（最近 10 条，每条截 200 字）
    if messages:
        lines = []
        for msg in messages[-10:]:
            role = "用户" if msg.get("role") == "user" else "助手"
            content = msg.get("content", "")[:200]
            lines.append(f"{role}: {content}")
        history_text = "\n".join(lines)
    else:
        history_text = "（无历史对话）"

    prompt = load_prompt(
        "decompose",
        today=date.today().isoformat(),
        history=history_text,
        user_query=user_query,
    )

    response = llm_client.chat(
        [{"role": "user", "content": prompt}],
        trace_id=trace_id,
    )
    sub_queries = _parse_json_array(response)

    logger.info("[{}] 查询分解完成 | sub_queries={}", trace_id, sub_queries)
    return {"sub_queries": sub_queries}


def _parse_json_array(text: str) -> list[SubQuery]:
    """安全解析 LLM 返回的 JSON 数组（复用现有逻辑）"""
    text = text.strip()
    # 移除 markdown 代码块标记
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            result = []
            for item in parsed:
                if isinstance(item, dict) and "type" in item and "query" in item:
                    result.append(SubQuery(type=item["type"], query=item["query"]))
            return result
        return []
    except json.JSONDecodeError:
        logger.warning("LLM 输出 JSON 解析失败: {}", text[:300])
        return []


# ============================================================================
# 条件边：分解后路由
# ============================================================================
def route_after_decompose(state: MainState):
    """
    根据子查询列表决定路由:
    - 无子查询 → 直接到 aggregate
    - 有子查询 → 直接 Send 到对应 Agent（跳过中间 agent_router）
    """
    sub_queries = state.get("sub_queries", [])
    if not sub_queries:
        logger.info("[{}] 无子查询 → 直接聚合", state.get("thread_id", "unknown"))
        return "aggregate"

    sends = []
    for sq in sub_queries:
        sq_type = sq.get("type", "general")
        target = "order_agent" if sq_type == "order" else "product_agent"
        logger.info("[{}] Send → {} | query={}",
                    state.get("thread_id", "unknown"), target, sq.get("query", "")[:50])
        sends.append(Send(target, {"sub_query": sq}))
    return sends


# ============================================================================
# Agent 节点
# ============================================================================
async def product_agent_node(state: MainState) -> dict:
    """
    调用 ProductAgent 执行商品子查询。
    结果通过 operator.add reducer 自动追加到 state.sub_results。

    注意: 每个并行分支有独立的 state，此节点的 state 是 Send 提供的副本。
    """
    from agents.product_agent_client import ProductAgent

    sub_query = state.get("sub_query", {})
    thread_id = state.get("thread_id", "unknown")

    agent = ProductAgent()
    try:
        result = await agent.process(
            user_query=sub_query.get("query", ""),
            trace_id=thread_id,
        )
    except Exception as e:
        logger.error("[{}] ProductAgent 执行异常 | {}", thread_id, str(e))
        result = {
            "task_id": "error",
            "task_type": "product",
            "status": "error",
            "data": [],
            "total": 0,
            "summary": "",
            "params_used": {},
            "error": str(e),
        }

    # 附加元数据
    result["_sub_type"] = sub_query.get("type", "product")
    result["_sub_query"] = sub_query.get("query", "")

    logger.info("[{}] ProductAgent 完成 | status={}", thread_id, result.get("status"))
    return {"sub_results": [result]}


async def order_agent_node(state: MainState) -> dict:
    """
    调用 OrderAgent 执行订单子查询。
    结果通过 operator.add reducer 自动追加到 state.sub_results。
    """
    from agents.order_agent_client import OrderAgent

    sub_query = state.get("sub_query", {})
    thread_id = state.get("thread_id", "unknown")

    agent = OrderAgent()
    try:
        result = await agent.process(
            user_query=sub_query.get("query", ""),
            trace_id=thread_id,
        )
    except Exception as e:
        logger.error("[{}] OrderAgent 执行异常 | {}", thread_id, str(e))
        result = {
            "task_id": "error",
            "task_type": "order",
            "status": "error",
            "data": [],
            "total": 0,
            "summary": "",
            "params_used": {},
            "error": str(e),
        }

    result["_sub_type"] = sub_query.get("type", "order")
    result["_sub_query"] = sub_query.get("query", "")

    logger.info("[{}] OrderAgent 完成 | status={}", thread_id, result.get("status"))
    return {"sub_results": [result]}


# ============================================================================
# 聚合节点
# ============================================================================
async def aggregate_node(state: MainState, config: RunnableConfig = None) -> dict:
    """
    调用 LLM 汇总所有子 Agent 的结果，生成最终自然语言回复。

    输入: state.sub_results, state.user_query
    输出: {final_response: str}

    v2.1: 当 config["configurable"]["token_queue"] 存在时，使用 chat_stream
          逐 token 推送，实现前端流式渲染。
    """
    sub_results = state.get("sub_results", [])
    user_query = state.get("user_query", "")
    thread_id = state.get("thread_id", "unknown")

    # 获取 token 队列（流式输出通道，从 LangGraph RunnableConfig 中提取）
    token_queue = None
    if config is not None:
        cfg = config.get("configurable", {})
        if cfg:
            token_queue = cfg.get("token_queue")

    if not sub_results:
        # v2.1: 优先检查澄清追问 — 直接返回，无需 LLM 再生成
        clarification_question = state.get("clarification_question", "")
        if clarification_question:
            if token_queue is not None:
                # 澄清追问也逐字流式推送
                for ch in clarification_question:
                    await token_queue.put(ch)
                await token_queue.put(None)
            return {"final_response": clarification_question}

        # 无子任务：可能是问候/闲聊/无法理解。用 LLM 生成友好回复。
        chat_prompt = f"""当前日期: {date.today().isoformat()}
用户说: "{user_query}"
请以 SmartShop 智能电商导购助手的身份友好回复。
- 如果是问候（如"你好""嗨"），热情打招呼并介绍你能帮忙搜索商品、比价推荐和查询订单
- 如果是感谢/道别，礼貌回应
- 如果是问"你是谁""能做什么"，简单介绍你的能力
- 如果确实是无法理解的内容，引导用户尝试具体的购物查询（如"推荐蓝牙耳机""查我的订单"）
控制在 2-3 句话。"""
        messages = [{"role": "user", "content": chat_prompt}]

        if token_queue is not None:
            response_parts = []
            async for token in llm_client.chat_stream(messages, trace_id=thread_id):
                response_parts.append(token)
                await token_queue.put(token)
            await token_queue.put(None)  # 哨兵：token 流结束
            response = "".join(response_parts)
        else:
            response = llm_client.chat(messages, trace_id=thread_id)

        return {"final_response": response.strip()}

    # 构建子结果文本
    parts = []
    for r in sub_results:
        sub_type = r.get("_sub_type", "unknown")
        sub_query = r.get("_sub_query", "")
        status = r.get("status", "error")

        if status == "success":
            summary = r.get("summary", "")
            parts.append(f"[{sub_type}] 查询: {sub_query}\n结果: {summary}")
        else:
            error = r.get("error", "未知错误")
            parts.append(f"[{sub_type}] 查询: {sub_query}\n状态: 失败 — {error}")

    sub_text = "\n\n---\n\n".join(parts)

    prompt = load_prompt(
        "aggregate",
        user_query=user_query,
        sub_results=sub_text,
    )
    messages = [{"role": "user", "content": prompt}]

    if token_queue is not None:
        response_parts = []
        async for token in llm_client.chat_stream(messages, trace_id=thread_id):
            response_parts.append(token)
            await token_queue.put(token)
        await token_queue.put(None)  # 哨兵：token 流结束
        response = "".join(response_parts)
    else:
        response = llm_client.chat(messages, trace_id=thread_id)

    logger.info("[{}] 聚合完成 | response_len={}", thread_id, len(response))
    return {"final_response": response.strip()}
