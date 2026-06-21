"""
=============================================================================
大模型调用统一封装
=============================================================================
适配 DeepSeek / Qwen 等国产大模型，兼容 OpenAI 接口规范。
提供统一的 chat / chat_stream 方法，配置文件中可切换模型。

v2.1: 新增 chat_stream() 支持 Token 级流式输出（基于 AsyncOpenAI）。
=============================================================================
"""

from typing import Optional, List, Dict, Any, AsyncGenerator
from openai import OpenAI, AsyncOpenAI
from loguru import logger

from config import LLM_CONFIG


class LLMClient:
    """大模型调用客户端（单例）"""

    _instance: Optional["LLMClient"] = None
    _client: Optional[OpenAI] = None
    _async_client: Optional[AsyncOpenAI] = None

    def __new__(cls) -> "LLMClient":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def _get_client(self) -> OpenAI:
        if self._client is None:
            self._client = OpenAI(
                api_key=LLM_CONFIG["api_key"],
                base_url=LLM_CONFIG["api_base"],
                timeout=LLM_CONFIG["request_timeout"],
            )
            logger.info("LLM 客户端初始化完成 | model={} | base_url={}",
                        LLM_CONFIG["model"], LLM_CONFIG["api_base"])
        return self._client

    def _get_async_client(self) -> AsyncOpenAI:
        """获取异步客户端实例（用于 streaming）"""
        if self._async_client is None:
            self._async_client = AsyncOpenAI(
                api_key=LLM_CONFIG["api_key"],
                base_url=LLM_CONFIG["api_base"],
                timeout=LLM_CONFIG["request_timeout"],
            )
            logger.info("LLM 异步客户端初始化完成 | model={}", LLM_CONFIG["model"])
        return self._async_client

    def chat(
        self,
        messages: List[Dict[str, str]],
        trace_id: str = "unknown",
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """
        调用大模型完成对话（同步，返回完整回复）。

        Args:
            messages:    标准 OpenAI 格式消息列表 [{"role": "user", "content": "..."}, ...]
            trace_id:    全链路追踪 ID
            temperature: 温度参数（默认使用配置值）
            max_tokens:  最大输出 token 数

        Returns:
            模型回复文本

        Raises:
            RuntimeError: 调用失败时抛出
        """
        client = self._get_client()

        try:
            logger.info("[{}] LLM 调用开始 | 消息数={} | model={}",
                        trace_id, len(messages), LLM_CONFIG["model"])

            response = client.chat.completions.create(
                model=LLM_CONFIG["model"],
                messages=messages,
                temperature=temperature or LLM_CONFIG["temperature"],
                max_tokens=max_tokens or LLM_CONFIG["max_tokens"],
            )

            content = response.choices[0].message.content
            logger.info("[{}] LLM 调用完成 | 回复长度={} | tokens={}",
                        trace_id, len(content) if content else 0,
                        response.usage.total_tokens if response.usage else "N/A")

            return content or ""

        except Exception as e:
            logger.error("[{}] LLM 调用失败: {}", trace_id, str(e))
            raise RuntimeError(f"大模型调用失败: {e}") from e

    async def chat_stream(
        self,
        messages: List[Dict[str, str]],
        trace_id: str = "unknown",
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> AsyncGenerator[str, None]:
        """
        调用大模型完成对话（异步流式，逐 token 产出）。

        Args:
            messages:    标准 OpenAI 格式消息列表
            trace_id:    全链路追踪 ID
            temperature: 温度参数（默认使用配置值）
            max_tokens:  最大输出 token 数

        Yields:
            每个 token 的文本增量

        Raises:
            RuntimeError: 调用失败时抛出
        """
        client = self._get_async_client()

        try:
            logger.info("[{}] LLM 流式调用开始 | 消息数={} | model={}",
                        trace_id, len(messages), LLM_CONFIG["model"])

            response = await client.chat.completions.create(
                model=LLM_CONFIG["model"],
                messages=messages,
                temperature=temperature or LLM_CONFIG["temperature"],
                max_tokens=max_tokens or LLM_CONFIG["max_tokens"],
                stream=True,
            )

            token_count = 0
            async for chunk in response:
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta and delta.content:
                    token_count += 1
                    yield delta.content

            logger.info("[{}] LLM 流式调用完成 | token 数={}",
                        trace_id, token_count)

        except Exception as e:
            logger.error("[{}] LLM 流式调用失败: {}", trace_id, str(e))
            raise RuntimeError(f"大模型流式调用失败: {e}") from e


# 全局 LLM 客户端实例
llm_client = LLMClient()
