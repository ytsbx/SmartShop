"""
=============================================================================
通用 MCP 客户端（官方 MCP SDK）
=============================================================================
基于官方 mcp 库实现 SSE 传输的 MCP 工具调用。
使用 sse_client + ClientSession 替代手写 JSON-RPC 协议。
=============================================================================
"""

import asyncio
import uuid
from typing import Optional, Dict, Any, Union

from loguru import logger
from mcp.client.sse import sse_client
from mcp import ClientSession

from config import A2A_CONFIG, MCP_CLIENT_CONFIG


class MCPClient:
    """
    MCP 通用客户端（官方 SDK 实现）。
    通过 SSE 传输协议向 MCP 服务端发起工具调用。
    """

    def __init__(self, server_url: str):
        """
        Args:
            server_url: MCP 服务端地址，如 "http://127.0.0.1:8100"
        """
        self.server_url = server_url.rstrip("/")

    async def call_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        trace_id: str = "unknown",
    ) -> Dict[str, Any]:
        """
        调用 MCP 服务端注册的工具（异步，SSE 传输）。

        Args:
            tool_name:  工具名称，如 "query_product" / "query_order"
            arguments:  工具参数字典
            trace_id:   全链路追踪 ID

        Returns:
            工具执行结果字典

        Raises:
            RuntimeError: 通信失败或服务端返回错误
        """
        sse_url = f"{self.server_url}/mcp/sse"
        logger.info("[{}] MCP 调用 | server={} | tool={} | args={}",
                    trace_id, self.server_url, tool_name, arguments)

        retries = A2A_CONFIG["max_retries"]
        last_error = None

        for attempt in range(1, retries + 2):  # 1 initial + N retries
            try:
                async with asyncio.timeout(MCP_CLIENT_CONFIG["sse_read_timeout"]):
                    async with sse_client(sse_url) as (read_stream, write_stream):
                        async with ClientSession(read_stream, write_stream) as session:
                            await session.initialize()
                            result = await session.call_tool(tool_name, arguments=arguments)
                            parsed = self._parse_result(result)
                            logger.info("[{}] MCP 调用成功 | tool={} | fields={}",
                                        trace_id, tool_name, len(parsed) if isinstance(parsed, dict) else 0)
                            return parsed

            except asyncio.TimeoutError:
                last_error = f"SSE 连接超时 ({MCP_CLIENT_CONFIG['sse_read_timeout']}s)"
                logger.warning("[{}] MCP 调用超时 (attempt {}/{}) | {}",
                               trace_id, attempt, retries + 1, last_error)
            except ConnectionError as e:
                last_error = e
                logger.warning("[{}] MCP 连接失败 (attempt {}/{}) | {}",
                               trace_id, attempt, retries + 1, str(e))
            except Exception as e:
                last_error = e
                logger.error("[{}] MCP 调用异常 | {}", trace_id, str(e))

            if attempt <= retries:
                await asyncio.sleep(A2A_CONFIG["retry_delay"])

        raise RuntimeError(f"MCP 调用失败（已重试 {retries} 次）: {last_error}")

    async def close(self) -> None:
        """关闭客户端（SSE 会话为临时连接，此处为空操作）"""
        pass

    def _parse_result(self, result) -> Dict[str, Any]:
        """
        将 ClientSession.call_tool() 返回的 CallToolResult 解析为字典格式。

        MCP SDK 1.x 的 CallToolResult.content 是 content block 列表，主流形式:
        - TextContent(type="text", text="...")
        - 也可能是 dict 形式 {"type": "text", "text": "..."}

        兼容多种提取路径，确保数据不丢失。
        """
        import json

        try:
            content = getattr(result, "content", None)
            if content is None:
                logger.warning("MCP result 无 content 字段 | result={}", str(result)[:200])
                return {}

            if not isinstance(content, list) or len(content) == 0:
                logger.warning("MCP result.content 为空或非列表 | type={}", type(content).__name__)
                return {}

            first = content[0]

            # ---- 路径 1: Pydantic model, 有 .text 属性 ----
            if hasattr(first, "text"):
                text = first.text
                return self._parse_text_content(text)

            # ---- 路径 2: dict 形式 {"type":"text","text":"..."} ----
            if isinstance(first, dict):
                text = first.get("text", "")
                if text:
                    return self._parse_text_content(text)
                # 也许整个 dict 本身就是我们要的数据
                return first

            # ---- 路径 3: model_dump / dict 方法 ----
            if hasattr(first, "model_dump"):
                dumped = first.model_dump()
                text = dumped.get("text", "")
                if text:
                    return self._parse_text_content(text)
                return dumped

            if hasattr(first, "dict"):
                dumped = first.dict()
                text = dumped.get("text", "")
                if text:
                    return self._parse_text_content(text)
                return dumped

            # ---- 最后的兜底 ----
            logger.warning("MCP content block 格式未知 | type={} | str={}",
                          type(first).__name__, str(first)[:300])
            return {"_raw": str(content)}

        except Exception as e:
            logger.error("MCP result 解析异常: {}", str(e))
            return {"_raw": str(result)}

    @staticmethod
    def _parse_text_content(text: str) -> Dict[str, Any]:
        """解析 text 内容：尝试 JSON 解析，失败则原样存入 _raw"""
        import json
        text = text.strip()
        if not text:
            logger.warning("_parse_text_content: 文本为空")
            return {}
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                logger.debug("_parse_text_content: JSON 解析成功, keys={}, total={}, data_len={}",
                           list(parsed.keys()), parsed.get('total', '?'), len(parsed.get('data', [])))
                return parsed
            # JSON 数组等非 dict 类型
            logger.warning("_parse_text_content: 解析结果非 dict, type={}", type(parsed).__name__)
            return {"_raw": text, "data": parsed if isinstance(parsed, list) else [parsed]}
        except (json.JSONDecodeError, TypeError) as e:
            logger.error("_parse_text_content: JSON 解析失败! type={}, 前200字符: {}",
                        type(e).__name__, text[:200])
            return {"_raw": text}

    async def list_tools(self) -> list:
        """列出 MCP 服务端所有可用工具（调试用）。"""
        sse_url = f"{self.server_url}/mcp/sse"
        async with sse_client(sse_url) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                tools_result = await session.list_tools()
                return [{"name": t.name, "description": t.description} for t in tools_result.tools]
