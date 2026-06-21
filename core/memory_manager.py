"""
=============================================================================
会话记忆辅助工具
=============================================================================
提供消息裁剪等纯函数，不涉及 checkpoint 管理。
checkpoint 由 LangGraph 官方 AsyncSqliteSaver.from_conn_string 直接管理（见 router 的 lifespan）。

使用方式：
    from core.memory_manager import trim_messages
    messages = trim_messages(messages, max_count=20)
=============================================================================
"""

from typing import Optional
from config import LANGGRAPH_CONFIG


def trim_messages(
    messages: list[dict],
    max_count: Optional[int] = None,
) -> list[dict]:
    """
    滑动窗口裁剪消息列表。

    当消息数量超过 max_count 时，保留最近的 max_count 条。
    不改变消息内容，仅做数量控制。

    Args:
        messages:   原始消息列表
        max_count:  最大保留数量，默认从 config 读取

    Returns:
        裁剪后的消息列表
    """
    limit = max_count or LANGGRAPH_CONFIG["max_history_messages"]
    if len(messages) > limit:
        return messages[-limit:]
    return messages
