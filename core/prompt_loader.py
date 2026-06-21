"""
=============================================================================
Prompt 模板加载器
=============================================================================
基于 string.Template 的轻量 Prompt 管理，不依赖 LangChain。
所有 Prompt 模板存放在 prompts/ 目录下，以 .txt 格式存储。

使用方式:
    from core.prompt_loader import load_prompt
    prompt = load_prompt("decompose", today="2026-06-17", history="...", user_query="...")
=============================================================================
"""

from string import Template
from pathlib import Path
from typing import Any

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


def load_prompt(name: str, **kwargs: Any) -> str:
    """
    加载 Prompt 模板并替换变量。

    Args:
        name: 模板名称（不含 .txt 后缀），如 "decompose"、"aggregate"
        **kwargs: 模板变量键值对

    Returns:
        替换后的 Prompt 字符串

    使用 safe_substitute 确保缺少变量时保留占位符而非抛异常，便于调试。
    """
    path = PROMPTS_DIR / f"{name}.txt"
    if not path.exists():
        raise FileNotFoundError(f"Prompt 模板不存在: {path}")

    template = Template(path.read_text(encoding="utf-8"))
    return template.safe_substitute(**kwargs)
