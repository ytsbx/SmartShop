"""
=============================================================================
ReAct（Reasoning + Acting）循环引擎 — v2.1
=============================================================================
通用 ReAct 循环实现，让 Agent 自主决策：
  - 需要调用哪个 MCP 工具？传什么参数？
  - 工具返回结果后，信息是否足够？
  - 需要调整参数重试，还是可以直接输出最终回答？

设计：
  - 引擎只负责循环逻辑与 JSON 解析，不涉及领域知识
  - 工具定义、执行函数由外部注入
  - 每次迭代：LLM 输出 {thought, action, action_input} 或 {thought, final_answer}
  - 引擎执行 action → observation 追加到对话 → 下一轮
  - 最大 N 轮后强制输出

使用方式:
    from core.react_loop import ReActEngine
    from core.mcp_client import MCPClient

    engine = ReActEngine(
        agent_type="商品搜索与推荐",
        tool_definitions=[{name, description, parameters}],
        tool_executor=my_executor,
    )
    answer = await engine.run("推荐一款蓝牙耳机", trace_id="xxx")
=============================================================================
"""

import json
import re
from typing import List, Dict, Any, Callable, Awaitable

from loguru import logger

from core.llm_utils import llm_client
from config import REACT_CONFIG

# 工具执行回调类型: async (tool_name, arguments, trace_id) -> dict
ToolExecutor = Callable[[str, Dict[str, Any], str], Awaitable[Dict[str, Any]]]

# ReAct 系统 Prompt 模板（通过 .format() 注入 agent_type / tool_definitions / max_iterations）
SYSTEM_PROMPT = """你是一个{agent_type}专家助手。你可以使用以下工具来获取信息：

{tool_definitions}

请遵循 ReAct（推理 → 行动 → 观察 → 推理）模式来解决问题。

每次回复必须是一个严格的 JSON 对象，格式为以下两种之一：

**需要调用工具时：**
{{"thought": "我需要做什么以及为什么", "action": "工具名称", "action_input": {{"参数名": "参数值"}}}}

**已有足够信息可以回答时：**
{{"thought": "我已经收集了足够的信息", "final_answer": "完整的自然语言回答"}}

规则：
1. 先思考需要什么信息，然后决定调用哪个工具、传什么参数
2. 工具返回结果后，仔细分析数据。如果为空或不理想，调整参数重试（如扩大范围、更换关键词、去掉限制条件）
3. 你最多可以调用 {max_iterations} 轮工具，之后必须给出最终回答
4. 如果已有足够信息回答用户，直接输出 final_answer
5. 最终回答应该用自然、友好的中文，像一个专业的导购顾问在说话
6. 最终回答要包含具体数据（商品名、价格、评分、销量等数字信息），不要泛泛而谈
7. 如果用户查询中使用了"我""我的"且没有提供具体姓名，在订单查询时将 customer_name 留空（服务端会返回不做姓名限制的记录）
8. 仅输出 JSON，不要输出其他任何内容"""


class ReActEngine:
    """通用 ReAct 循环执行器。"""

    def __init__(
        self,
        agent_type: str,
        tool_definitions: List[Dict[str, Any]],
        tool_executor: ToolExecutor,
        max_iterations: int = None,
    ):
        """
        Args:
            agent_type:       Agent 类型描述，如 "商品搜索与推荐"
            tool_definitions: 可用工具列表 [{"name": ..., "description": ..., "parameters": {...}}]
            tool_executor:    async callable (tool_name, arguments, trace_id) -> observation dict
            max_iterations:   最大迭代次数，默认从 REACT_CONFIG 读取
        """
        self.agent_type = agent_type
        self.tool_definitions = tool_definitions
        self.tool_executor = tool_executor
        self.max_iterations = max_iterations or REACT_CONFIG["max_iterations"]

    def _build_system_prompt(self) -> str:
        """构建包含工具定义的系统提示。"""
        tool_descriptions = []
        for td in self.tool_definitions:
            name = td["name"]
            desc = td.get("description", "")
            params = td.get("parameters", {})
            param_lines = []
            for pname, pdesc in params.items():
                param_lines.append(f"      {pname}: {pdesc}")
            params_text = "\n".join(param_lines) if param_lines else "      （无参数）"
            tool_descriptions.append(
                f"  - {name}: {desc}\n    参数：\n{params_text}"
            )
        tools_text = "\n".join(tool_descriptions)

        return SYSTEM_PROMPT.format(
            agent_type=self.agent_type,
            tool_definitions=tools_text,
            max_iterations=self.max_iterations,
        )

    async def run(self, user_query: str, trace_id: str = "unknown") -> str:
        """
        执行 ReAct 循环，返回最终自然语言回答。

        Args:
            user_query: 用户的自然语言查询
            trace_id:   全链路追踪 ID

        Returns:
            Agent 的最终自然语言回答文本
        """
        messages = [
            {"role": "system", "content": self._build_system_prompt()},
            {"role": "user", "content": user_query},
        ]

        for iteration in range(1, self.max_iterations + 2):  # +1 容错
            response = llm_client.chat(messages, trace_id=trace_id)
            parsed = self._parse_response(response)

            # 最终回答
            if "final_answer" in parsed:
                logger.info("[{}] ReAct 第{}轮 → 最终回答 (len={})",
                            trace_id, iteration, len(parsed["final_answer"]))
                return parsed["final_answer"]

            # 工具调用
            if "action" in parsed:
                action = parsed["action"]
                action_input = parsed.get("action_input", {})
                thought = parsed.get("thought", "")

                logger.info("[{}] ReAct 第{}轮 → action={} | thought={}",
                            trace_id, iteration, action, thought[:100])

                # 执行工具
                try:
                    observation = await self.tool_executor(action, action_input, trace_id)
                except Exception as e:
                    observation = {"error": f"工具执行异常: {str(e)}"}
                    logger.error("[{}] ReAct 工具执行失败 | {}", trace_id, str(e))

                obs_text = json.dumps(observation, ensure_ascii=False, default=str)
                # 截断过长观察（防止上下文爆炸）
                if len(obs_text) > 3000:
                    obs_text = obs_text[:3000] + f"...(共{len(obs_text)}字符，已截断)"

                messages.append({"role": "assistant", "content": response})
                messages.append({"role": "user", "content": f"工具执行结果：\n{obs_text}"})
                continue

            # 无法解析：当作最终回答
            logger.warning("[{}] ReAct 第{}轮 无法解析响应，当作最终回答 | raw={}",
                           trace_id, iteration, response[:200])
            return response

        # 达到最大迭代：强制要求输出回答
        logger.warning("[{}] ReAct 达到最大迭代 {}，强制生成最终回答",
                       trace_id, self.max_iterations)
        messages.append({
            "role": "user",
            "content": (
                "已达到最大工具调用次数。请基于已有信息，直接输出最终回答。"
                "格式：{\"thought\": \"...\", \"final_answer\": \"...\"}"
            ),
        })
        final_response = llm_client.chat(messages, trace_id=trace_id)
        parsed = self._parse_response(final_response)
        return parsed.get("final_answer", final_response)

    @staticmethod
    def _parse_response(text: str) -> Dict[str, Any]:
        """
        安全解析 LLM 的 JSON 响应。多重回退策略：
        1. 直接 JSON 解析
        2. Strip markdown code fence 后解析
        3. 正则提取 JSON 对象
        4. 兜底：将原始文本当作 final_answer
        """
        text = text.strip()

        # 策略 1 & 2：直接解析 / strip fence
        candidates = [text]
        if text.startswith("```"):
            lines = text.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            candidates.append("\n".join(lines).strip())

        for candidate in candidates:
            try:
                return json.loads(candidate)
            except (json.JSONDecodeError, TypeError):
                continue

        # 策略 3：正则提取 JSON 对象
        try:
            match = re.search(r'\{[^{}]*"action"|\{.*?"final_answer".*?\}', text, re.DOTALL)
            if match:
                return json.loads(match.group())
        except (json.JSONDecodeError, TypeError, AttributeError):
            pass

        # 策略 4：兜底 — 原始文本当回答
        logger.warning("ReAct response JSON 全部解析策略失败，兜底为 raw text")
        return {"final_answer": text}
