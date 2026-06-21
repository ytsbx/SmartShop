"""
=============================================================================
A2A 主路由服务端（FastAPI 后端）— v2.0 LangGraph 编排
=============================================================================
独立的 HTTP 服务进程，负责：
  1. 接收前端（Streamlit）发来的用户查询与对话历史
  2. 通过 LangGraph 编排流程: 查询分解 → Agent 并行调度 → 结果聚合
  3. 支持 SSE 流式输出，按节点逐步推送进度与结果
  4. 支持同步 POST /api/chat（兼容旧版）

对外暴露 REST API：
  POST /api/chat        — 聊天接口（同步，兼容旧版）
  GET  /api/chat/stream — 聊天接口（SSE 流式，新）
  GET  /api/health      — 健康检查
  GET  /api/services    — 下游服务状态

启动方式:
    python -m uvicorn core.router_A2Aagent_Server:app --host 127.0.0.1 --port 8008
=============================================================================
"""

import sys
import os
import uuid
import json
import time
import asyncio
from contextlib import asynccontextmanager
from typing import List, Dict, Any, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from loguru import logger

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from core.llm_utils import llm_client
from core.logger import setup_logger
from core.mcp_client import MCPClient
from core.graph import build_graph
from core.state import MainState
from config import (
    MCP_PRODUCT_SERVER,
    MCP_ORDER_SERVER,
    A2A_CONFIG,
    LANGGRAPH_CONFIG,
    STREAM_CONFIG,
)

setup_logger()

# ============================================================================
# LangGraph 图实例（通过 lifespan 异步初始化，与 AsyncSqliteSaver 兼容）
# ============================================================================
graph = None  # 延迟到 lifespan 中通过 await build_graph() 初始化


@asynccontextmanager
async def lifespan(application: FastAPI):
    """应用生命周期：启动时初始化 LangGraph 图（AsyncSqliteSaver），关闭时释放 aiosqlite 连接"""
    global graph
    db_path = LANGGRAPH_CONFIG["checkpoint_db"]
    logger.info("初始化 LangGraph 编排图 (AsyncSqliteSaver) | db={}", db_path)
    async with AsyncSqliteSaver.from_conn_string(db_path) as checkpointer:
        graph = build_graph(checkpointer)
        logger.info("LangGraph 编排图初始化完成")
        yield
    logger.info("LangGraph 图生命周期结束，aiosqlite 连接已释放")


# ============================================================================
# FastAPI 应用
# ============================================================================
app = FastAPI(
    title="SmartShop A2A Router Server",
    version="2.0.0",
    description="SmartShop 核心后端服务 — LangGraph 编排 / SSE 流式输出",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# Pydantic 请求/响应模型（保持旧版兼容）
# ============================================================================
class ChatRequest(BaseModel):
    """前端聊天请求"""
    query: str = Field(..., min_length=1, max_length=2000, description="用户查询文本")
    history: Optional[List[Dict[str, str]]] = Field(
        default=None,
        description="对话历史 [{'role':'user/assistant','content':'...'}]"
    )
    thread_id: Optional[str] = Field(
        default=None,
        description="会话标识（用于 checkpoint 恢复，不传则自动生成）"
    )


class ChatResponse(BaseModel):
    """后端聊天响应"""
    trace_id: str
    answer: str
    sub_tasks: List[Dict[str, Any]] = []
    status: str = "success"  # success / partial / error
    elapsed_seconds: float = 0.0


def _determine_status(sub_results: list) -> str:
    """根据子任务结果判断整体状态"""
    if not sub_results:
        return "success"
    errors = [r for r in sub_results if r.get("status") == "error"]
    if len(errors) == len(sub_results):
        return "error"
    elif errors:
        return "partial"
    return "success"


# ============================================================================
# REST API — 同步端点（兼容旧版）
# ============================================================================
@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    """
    核心聊天接口（同步）。
    使用 LangGraph 图编排：查询分解 → Agent 并行 → 结果聚合。
    """
    trace_id = request.thread_id or str(uuid.uuid4())[:12]
    start_time = time.time()

    logger.info("=" * 60)
    logger.info("[{}] === 收到聊天请求 ===", trace_id)
    logger.info("[{}] query={}", trace_id, request.query[:200])

    try:
        # 构建初始状态
        messages = request.history or []
        # 追加当前用户消息
        messages.append({"role": "user", "content": request.query})

        initial_state: MainState = {
            "messages": messages,
            "user_query": request.query,
            "sub_queries": [],
            "sub_results": [],
            "final_response": "",
            "thread_id": trace_id,
        }

        config = {"configurable": {"thread_id": trace_id}}
        result = await graph.ainvoke(initial_state, config=config)

        elapsed = time.time() - start_time
        sub_results = result.get("sub_results", [])
        final_answer = result.get("final_response", "")
        status = _determine_status(sub_results)

        logger.info("[{}] === 聊天请求完成 | 耗时={:.2f}s | status={} ===",
                    trace_id, elapsed, status)

        return ChatResponse(
            trace_id=trace_id,
            answer=final_answer,
            sub_tasks=sub_results,
            status=status,
            elapsed_seconds=round(elapsed, 2),
        )

    except Exception as e:
        elapsed = time.time() - start_time
        logger.error("[{}] API 处理异常: {}", trace_id, str(e))
        raise HTTPException(status_code=500, detail=f"服务端内部错误: {e}")


# ============================================================================
# REST API — SSE 流式端点（v2.1: 双队列并发架构，支持 Token 级流式输出）
# ============================================================================
@app.get("/api/chat/stream")
async def chat_stream_endpoint(
    query: str = Query(..., min_length=1, max_length=2000),
    thread_id: Optional[str] = Query(default=None),
    history: Optional[str] = Query(default=None, description="JSON 编码的对话历史"),
):
    """
    聊天接口（SSE 流式，v2.1 双队列并发架构）。

    SSE 事件类型:
    - event: progress     → 查询分解完成
    - event: sub_result   → 单个 Agent 执行完成
    - event: token        → Token 级流式输出（逐字推送，v2.1 新增）
    - event: final        → 聚合完成（含完整响应文本，兼容前端）
    - event: error        → 异常
    - event: done         → 流结束

    前端可通过 EventSource 消费。
    """
    trace_id = thread_id or str(uuid.uuid4())[:12]
    logger.info("[{}] === 收到流式聊天请求 ===", trace_id)
    logger.info("[{}] query={}", trace_id, query[:200])

    # 解析历史
    messages = []
    if history:
        try:
            messages = json.loads(history)
        except json.JSONDecodeError:
            pass
    messages.append({"role": "user", "content": query})

    initial_state: MainState = {
        "messages": messages,
        "user_query": query,
        "sub_queries": [],
        "sub_results": [],
        "final_response": "",
        "thread_id": trace_id,
    }

    # 双队列：token_queue 用于 aggregate_node 写入 token，node_event_queue 用于 graph_runner 写入节点事件
    token_queue: asyncio.Queue = asyncio.Queue(maxsize=10000)
    node_event_queue: asyncio.Queue = asyncio.Queue()

    config = {
        "configurable": {
            "thread_id": trace_id,
            "token_queue": token_queue,
        }
    }

    async def graph_runner():
        """后台任务：运行 graph.astream() 并将节点事件推入 node_event_queue。"""
        try:
            async for chunk in graph.astream(
                initial_state,
                config=config,
                stream_mode="updates",
            ):
                await node_event_queue.put(("chunk", chunk))
            await node_event_queue.put(("graph_done", None))
        except Exception as e:
            logger.error("[{}] graph_runner 异常: {}", trace_id, str(e))
            await node_event_queue.put(("graph_error", str(e)))

    async def event_generator():
        """主生成器：并发 drain 两个队列，交织发射 SSE 事件。"""
        graph_task = asyncio.create_task(graph_runner())

        graph_done = False
        token_sentinel_seen = False
        pending_final = None  # aggregate 完成后暂存的 final_response
        poll_interval = STREAM_CONFIG["token_polling_interval"]

        try:
            while not graph_done:
                # ---- Drain 节点事件队列 ----
                while True:
                    try:
                        evt_type, evt_data = node_event_queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break

                    if evt_type == "graph_done":
                        graph_done = True
                        break
                    elif evt_type == "graph_error":
                        yield _sse_event("error", json.dumps(
                            {"error": evt_data}, ensure_ascii=False))
                        graph_done = True
                        break
                    elif evt_type == "chunk":
                        for node_name, node_output in evt_data.items():
                            if node_name == "clarify_query":
                                if node_output.get("needs_clarification"):
                                    yield _sse_event("clarification", json.dumps({
                                        "clarification_question": node_output.get("clarification_question", ""),
                                    }, ensure_ascii=False))

                            elif node_name == "decompose_query":
                                sqs = node_output.get("sub_queries", [])
                                yield _sse_event("progress", json.dumps({
                                    "node": "decompose",
                                    "sub_queries": sqs,
                                    "count": len(sqs),
                                    "msg": f"已分解为 {len(sqs)} 个子查询" if sqs else "未检测到需要查询的子任务"
                                }, ensure_ascii=False))

                            elif node_name in ("product_agent", "order_agent"):
                                sub_results = node_output.get("sub_results", [])
                                for sr in sub_results:
                                    yield _sse_event("sub_result", json.dumps({
                                        "task_id": sr.get("task_id", ""),
                                        "task_type": sr.get("task_type", node_name.replace("_agent", "")),
                                        "status": sr.get("status", "unknown"),
                                        "summary": sr.get("summary", ""),
                                        "data": sr.get("data", []),
                                        "total": sr.get("total", 0),
                                        "params_used": sr.get("params_used", {}),
                                        "error": sr.get("error"),
                                        "_sub_type": sr.get("_sub_type", ""),
                                        "_sub_query": sr.get("_sub_query", ""),
                                    }, ensure_ascii=False, default=str))

                            elif node_name == "aggregate":
                                pending_final = node_output.get("final_response", "")

                # ---- Drain token 队列（非阻塞）----
                while True:
                    try:
                        token = token_queue.get_nowait()
                        if token is None:
                            token_sentinel_seen = True
                            break
                        yield _sse_event("token", json.dumps({"token": token}))
                    except asyncio.QueueEmpty:
                        break

                if not graph_done:
                    await asyncio.sleep(poll_interval)

            # ---- Graph 完成，drain 剩余 token ----
            while not token_sentinel_seen:
                try:
                    token = token_queue.get_nowait()
                    if token is None:
                        break
                    yield _sse_event("token", json.dumps({"token": token}))
                except asyncio.QueueEmpty:
                    await asyncio.sleep(0.01)

            # ---- 发射 final 事件（兼容旧前端）----
            if pending_final:
                yield _sse_event("final", json.dumps({
                    "response": pending_final,
                }, ensure_ascii=False))

            yield _sse_event("done", "{}")

        except Exception as e:
            logger.error("[{}] SSE 流异常: {}", trace_id, str(e))
            yield _sse_event("error", json.dumps({"error": str(e)}, ensure_ascii=False))
            yield _sse_event("done", "{}")
        finally:
            if not graph_task.done():
                graph_task.cancel()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _sse_event(event: str, data: str) -> str:
    """构建 SSE 格式的消息"""
    return f"event: {event}\ndata: {data}\n\n"


# ============================================================================
# 健康检查
# ============================================================================
@app.get("/api/health")
async def health_check():
    """A2A 路由服务健康检查（异步探测下游 MCP 服务）"""
    product_status = "unknown"
    order_status = "unknown"

    # 探测 Product MCP
    try:
        client = MCPClient(MCP_PRODUCT_SERVER["url"])
        result = await client.call_tool("ping", {}, trace_id="health_check")
        product_status = "ok" if result.get("status") == "ok" else "error"
    except Exception:
        product_status = "unavailable"

    # 探测 Order MCP
    try:
        client = MCPClient(MCP_ORDER_SERVER["url"])
        result = await client.call_tool("ping", {}, trace_id="health_check")
        order_status = "ok" if result.get("status") == "ok" else "error"
    except Exception:
        order_status = "unavailable"

    return {
        "status": "healthy",
        "service": "a2a_router_server",
        "version": "2.0.0",
        "orchestration": "langgraph",
        "downstream": {
            "product_mcp": product_status,
            "order_mcp": order_status,
        },
    }


# ============================================================================
# 服务列表
# ============================================================================
@app.get("/api/services")
async def list_services():
    """列出下游服务与工具"""
    return {
        "router": "SmartShop A2A Router Server v2.0 (LangGraph)",
        "downstream_services": {
            "product_mcp": {
                "url": MCP_PRODUCT_SERVER["url"],
                "sse_url": MCP_PRODUCT_SERVER["sse_url"],
                "tools": ["query_product", "ping"],
            },
            "order_mcp": {
                "url": MCP_ORDER_SERVER["url"],
                "sse_url": MCP_ORDER_SERVER["sse_url"],
                "tools": ["query_order", "ping"],
            },
        },
    }


# ============================================================================
# 启动入口
# ============================================================================
if __name__ == "__main__":
    import uvicorn
    logger.info("=== SmartShop A2A Router Server v2.0 (LangGraph) 启动中 ===")
    uvicorn.run(app, host="0.0.0.0", port=8008, log_level="info")
