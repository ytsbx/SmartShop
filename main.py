"""
=============================================================================
SmartShop 智能电商导购助手 — Streamlit 交互入口（前端）v2.0
=============================================================================
标准聊天界面布局：
  - 顶部标题「SmartShop 智能电商导购助手」
  - 主体为对话展示区（支持多轮对话上下文保留）
  - SSE 流式输出：实时显示查询进度与中间结果
  - 支持同步 POST 回退（兼容模式）
  - 底部为输入框

架构位置：交互层 —— 通过 HTTP/SSE 调用 A2A Router Server（8008端口）

启动方式:
    streamlit run main.py
=============================================================================
"""

import sys
import os
import json
import uuid

import streamlit as st
import pandas as pd
import httpx
from loguru import logger

from core.logger import setup_logger
from config import STREAMLIT_CONFIG, A2A_ROUTER_SERVER, A2A_CONFIG

# 初始化日志
setup_logger()

# ============================================================================
# 页面配置
# ============================================================================
st.set_page_config(
    page_title=STREAMLIT_CONFIG["page_title"],
    page_icon=STREAMLIT_CONFIG["page_icon"],
    layout=STREAMLIT_CONFIG["layout"],
)

# ============================================================================
# 自定义 CSS 样式
# ============================================================================
st.markdown("""
<style>
    .main-title {
        font-size: 2rem;
        font-weight: 700;
        background: linear-gradient(135deg, #f093fb 0%, #f5576c 50%, #ffa751 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        text-align: center;
        margin-bottom: 1rem;
    }
    .sub-title {
        text-align: center;
        color: #888;
        font-size: 0.9rem;
        margin-bottom: 1.5rem;
    }
    .assistant-msg {
        background: linear-gradient(135deg, #f5f7fa 0%, #e4e8f0 100%);
        border-radius: 12px;
        padding: 1rem 1.2rem;
        margin: 0.5rem 0;
        border-left: 4px solid #f5576c;
    }
    .error-msg {
        background: #fff2f0;
        border: 1px solid #ffccc7;
        border-radius: 8px;
        padding: 0.8rem 1rem;
        color: #cf1322;
        margin: 0.5rem 0;
    }
    .sub-tag {
        display: inline-block;
        padding: 2px 8px;
        border-radius: 4px;
        font-size: 0.75rem;
        margin-right: 4px;
    }
    .tag-product { background: #e6f7ff; color: #1890ff; }
    .tag-order { background: #fff7e6; color: #fa8c16; }
    .status-box {
        padding: 0.6rem 0.8rem;
        border-radius: 8px;
        margin: 0.4rem 0;
        font-size: 0.85rem;
        background: #f0f5ff;
        border-left: 3px solid #f5576c;
    }
</style>
""", unsafe_allow_html=True)

# ============================================================================
# 会话状态初始化
# ============================================================================
if "messages" not in st.session_state:
    st.session_state.messages = []

if "thread_id" not in st.session_state:
    st.session_state.thread_id = str(uuid.uuid4())[:12]

if "trace_id" not in st.session_state:
    st.session_state.trace_id = None


# ============================================================================
# 后端通信函数
# ============================================================================
def call_backend(query: str, history: list, thread_id: str) -> dict:
    """
    通过 HTTP 调用 A2A Router Server 后端（同步，兼容旧版）。

    Args:
        query:    用户查询文本
        history:  对话历史列表
        thread_id: 会话标识

    Returns:
        后端响应字典 {trace_id, answer, sub_tasks, status, elapsed_seconds}

    Raises:
        RuntimeError: 后端不可达或调用超时
    """
    backend_url = f"{A2A_ROUTER_SERVER['url']}/api/chat"
    timeout = A2A_CONFIG["request_timeout"]

    payload = {
        "query": query,
        "history": history if history else None,
        "thread_id": thread_id,
    }

    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(backend_url, json=payload)
            response.raise_for_status()
            return response.json()

    except httpx.ConnectError:
        logger.error("后端服务不可达 | url={}", backend_url)
        raise RuntimeError(
            f"⚠️ 后端服务未启动，请先运行 A2A Router Server：\n\n"
            f"`python -m uvicorn core.router_A2Aagent_Server:app --host 127.0.0.1 --port 8008`"
        )
    except httpx.TimeoutException:
        logger.error("后端调用超时 | timeout={}s", timeout)
        raise RuntimeError("后端服务响应超时，请稍后重试。")
    except httpx.HTTPError as e:
        logger.error("后端 HTTP 异常: {}", str(e))
        raise RuntimeError(f"后端服务异常: {e}")


def stream_backend_sse(query: str, history: list, thread_id: str):
    """
    通过 SSE 流式调用后端，返回事件生成器。

    逐条 yield (event_type, data_dict)，供前端实时渲染。
    ConnectError / HTTP 异常通过 yield 一个 error 事件传递给调用方。

    Yields:
        (event_type: str, data: dict)
        事件类型: token | sub_result | clarification | final | error | done | progress
    """
    backend_url = f"{A2A_ROUTER_SERVER['url']}/api/chat/stream"
    timeout = A2A_CONFIG["request_timeout"] * 2

    params = {
        "query": query,
        "thread_id": thread_id,
    }
    if history:
        params["history"] = json.dumps(history, ensure_ascii=False)

    try:
        with httpx.Client(timeout=timeout) as client:
            with client.stream("GET", backend_url, params=params) as response:
                response.raise_for_status()

                current_event = None
                for line in response.iter_lines():
                    if not line:
                        current_event = None
                        continue
                    if line.startswith("event: "):
                        current_event = line[7:].strip()
                    elif line.startswith("data: "):
                        data_str = line[6:]
                        try:
                            data = json.loads(data_str)
                        except json.JSONDecodeError:
                            continue
                        yield (current_event, data)

    except httpx.ConnectError:
        yield ("error", {
            "error": f"⚠️ 后端服务未启动，请先运行 A2A Router Server：\n\n"
                     f"`python -m uvicorn core.router_A2Aagent_Server:app --host 127.0.0.1 --port 8008`"
        })
    except Exception as e:
        logger.error("SSE 流式调用异常: {}", str(e))
        yield ("error", {"error": str(e)})


def check_backend_health() -> dict:
    """检查后端及下游服务健康状态"""
    try:
        with httpx.Client(timeout=5) as client:
            response = client.get(f"{A2A_ROUTER_SERVER['url']}/api/health")
            return response.json()
    except Exception:
        return {"status": "unavailable"}


# ============================================================================
# 页面布局
# ============================================================================

# ---- 顶栏 ----
st.markdown('<div class="main-title">🛒 SmartShop 智能电商导购助手</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="sub-title">基于 LangGraph + MCP 架构 · 流式输出 · 一句话搜索商品与查询订单 · 支持多轮对话</div>',
    unsafe_allow_html=True,
)

# ---- 侧边栏 ----
with st.sidebar:
    st.markdown("### 📋 使用指南")
    st.markdown("""
**我能帮你做什么？**
- 🔍 **搜商品**：推荐一款蓝牙耳机
- 💰 **比价**：500 以内的机械键盘
- 📦 **查订单**：我的订单到哪了？
- 🏷️ **按分类逛**：有什么好的运动装备？
- 🔀 **复合查询**：帮我推荐一款扫地机器人，顺便查下我最近的订单

**小技巧：**
- 支持口语化提问（"有没有便宜点的""口碑好的"）
- 可以说 "那边的""那个" 等模糊指代追问
- 支持多轮对话上下文继承
    """)

    st.markdown("---")
    st.markdown("### 🔧 后端服务状态")

    health = check_backend_health()

    if health.get("status") == "healthy":
        st.success("🟢 A2A 路由后端")
        version = health.get("version", "unknown")
        st.caption(f"版本: {version} | 编排: {health.get('orchestration', 'unknown')}")

        downstream = health.get("downstream", {})
        product_status = downstream.get("product_mcp", "unknown")
        order_status = downstream.get("order_mcp", "unknown")

        st.markdown(
            f"🛍️ 商品 MCP: {'🟢' if product_status == 'ok' else '🔴' if product_status == 'unavailable' else '🟡'}"
        )
        st.markdown(
            f"📦 订单 MCP: {'🟢' if order_status == 'ok' else '🔴' if order_status == 'unavailable' else '🟡'}"
        )
    else:
        st.error("🔴 A2A 路由后端未启动")

    st.caption(f"会话 ID: {st.session_state.thread_id}")
    st.caption(f"最近 Trace: {st.session_state.trace_id or 'N/A'}")

    if st.button("🔄 清空对话"):
        st.session_state.messages = []
        st.session_state.trace_id = None
        st.session_state.thread_id = str(uuid.uuid4())[:12]
        st.rerun()

# ---- 对话展示区 ----
chat_container = st.container()

with chat_container:
    for msg in st.session_state.messages:
        if msg["role"] == "user":
            with st.chat_message("user", avatar="👤"):
                st.markdown(msg["content"])
        else:
            with st.chat_message("assistant", avatar="🤖"):
                st.markdown(msg["content"], unsafe_allow_html=False)

                # 如果有子任务详情，展开可查看
                if msg.get("sub_tasks"):
                    with st.expander("🔍 查看详细数据", expanded=False):
                        for task in msg["sub_tasks"]:
                            task_type = task.get("task_type", "")
                            tag_class = "tag-product" if task_type == "product" else "tag-order"
                            tag_label = "🛍️ 商品" if task_type == "product" else "📦 订单"

                            st.markdown(
                                f'<span class="sub-tag {tag_class}">{tag_label}</span> '
                                f'_{task.get("_sub_query", task.get("summary", ""))[:60]}_',
                                unsafe_allow_html=True,
                            )

                            if task.get("status") == "success" and task.get("data"):
                                df = pd.DataFrame(task["data"])
                                if not df.empty:
                                    st.dataframe(df, use_container_width=True, hide_index=True)
                            elif task.get("status") == "error":
                                st.warning(f"⚠️ {task.get('error', '查询失败')}")

# ---- 输入框 ----
if prompt := st.chat_input("请输入您的购物查询需求，例如：推荐一款蓝牙耳机"):
    # 显示用户消息
    st.session_state.messages.append({"role": "user", "content": prompt})

    with chat_container:
        with st.chat_message("user", avatar="👤"):
            st.markdown(prompt)

    # 构建对话历史（不含当前消息）
    history = [
        {"role": m["role"], "content": m["content"]}
        for m in st.session_state.messages[:-1]
    ]

    # 实时展示区：先在状态框内流式渲染，完成后再保存到历史
    with st.status("🤔 正在分析您的查询...", expanded=True) as status_box:
        status_box.write("📡 连接到后端服务...")

        accumulated = ""          # token 累积
        sub_tasks = []            # Agent 子结果
        final_answer = ""         # 最终完整回复（final 事件用）
        is_error = False
        use_stream = False

        try:
            # ---- 在 chat_message 内创建一个动态占位符，随 token 实时刷新 ----
            with chat_container:
                with st.chat_message("assistant", avatar="🤖"):
                    token_placeholder = st.empty()

                    # 尝试 SSE 流式
                    try:
                        use_stream = True
                        for event_type, data in stream_backend_sse(
                            query=prompt,
                            history=history,
                            thread_id=st.session_state.thread_id,
                        ):
                            if event_type == "progress":
                                # 查询分解进度
                                count = data.get("count", 0)
                                msg = data.get("msg", "")
                                status_box.write(f"🔍 {msg}")

                            elif event_type == "sub_result":
                                # Agent 子任务完成，追加数据
                                sub_tasks.append(data)
                                task_type = data.get("task_type", "")
                                summary = data.get("summary", "")[:50]
                                emoji = "🛍️" if task_type == "product" else "📦"
                                status_box.write(
                                    f"{emoji} {'商品' if task_type == 'product' else '订单'}查询完成: {summary}"
                                )

                            elif event_type == "clarification":
                                # 澄清追问 — 逐字流式
                                question = data.get("clarification_question", "")
                                accumulated = question  # 完整推送
                                token_placeholder.markdown(question)

                            elif event_type == "token":
                                # ✅ 核心：每个 token 立即刷新显示
                                accumulated += data.get("token", "")
                                token_placeholder.markdown(accumulated + "▌")

                            elif event_type == "final":
                                # 聚合最终回复（如果没走 token 流，这里作为兜底）
                                if not accumulated:
                                    final_answer = data.get("response", "")
                                    accumulated = final_answer
                                    token_placeholder.markdown(accumulated)

                            elif event_type == "error":
                                is_error = True
                                final_answer = data.get("error", "未知错误")
                                accumulated = final_answer
                                token_placeholder.error(f"😔 {final_answer}")
                                break

                            elif event_type == "done":
                                # 流正常结束
                                break

                    except Exception:
                        logger.warning("SSE 流式失败，回退到同步模式")
                        use_stream = False
                        result = call_backend(
                            query=prompt,
                            history=history,
                            thread_id=st.session_state.thread_id,
                        )
                        accumulated = result.get("answer", "")
                        sub_tasks = result.get("sub_tasks", [])
                        is_error = (result.get("status") == "error")
                        token_placeholder.markdown(accumulated)

                    # 移除光标闪烁符，展示最终文本
                    if accumulated and not is_error:
                        token_placeholder.markdown(accumulated)

            # ---- 流式结束后，追加子任务数据详情 ----
            if sub_tasks:
                with chat_container:
                    with st.chat_message("assistant", avatar="🤖"):
                        with st.expander("🔍 查看详细数据", expanded=False):
                            for task in sub_tasks:
                                task_type = task.get("task_type", "")
                                tag_class = "tag-product" if task_type == "product" else "tag-order"
                                tag_label = "🛍️ 商品" if task_type == "product" else "📦 订单"

                                st.markdown(
                                    f'<span class="sub-tag {tag_class}">{tag_label}</span> '
                                    f'_{task.get("_sub_query", task.get("summary", ""))[:60]}_',
                                    unsafe_allow_html=True,
                                )

                                if task.get("status") == "success" and task.get("data"):
                                    df = pd.DataFrame(task["data"])
                                    if not df.empty:
                                        st.dataframe(df, use_container_width=True, hide_index=True)
                                elif task.get("status") == "error":
                                    st.warning(f"⚠️ {task.get('error', '查询失败')}")

            # 最终状态
            if is_error:
                status_box.update(label="❌ 查询失败", state="error", expanded=False)
            else:
                status_box.update(
                    label=f"✅ 查询完成{' (流式)' if use_stream else ''}",
                    state="complete",
                    expanded=False,
                )

            # 保存到对话历史
            display_msg = accumulated
            if is_error:
                display_msg = f"😔 {display_msg}\n\n> 📎 错误追踪码: `{st.session_state.thread_id}`"
            st.session_state.messages.append({
                "role": "assistant",
                "content": display_msg,
                "sub_tasks": sub_tasks,
                "trace_id": st.session_state.thread_id,
            })

        except Exception as e:
            logger.error("Streamlit 前端异常: {}", str(e))
            status_box.update(label="❌ 系统异常", state="error", expanded=False)

            with chat_container:
                with st.chat_message("assistant", avatar="🤖"):
                    st.error(f"😔 抱歉，系统遇到了临时问题，请稍后重试。\n\n> 📎 错误信息: {str(e)[:200]}")

            st.session_state.messages.append({
                "role": "assistant",
                "content": f"😔 系统异常: {str(e)[:200]}",
                "sub_tasks": [],
            })

# ---- 底部 ----
st.markdown("---")
st.caption(
    "SmartShop v2.0 | 架构: Streamlit → LangGraph(8008) → Agent → MCP(8100/8101) → MySQL | "
    "LLM: DeepSeek | 数据: 模拟商品 + 模拟订单 | 输出: SSE 流式"
)
