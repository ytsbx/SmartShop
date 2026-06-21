"""
=============================================================================
日志配置模块
=============================================================================
基于 Loguru 的统一日志系统：
  - 按天切割日志文件
  - 全链路携带 trace_id
  - 记录调用流程、参数、错误详情
"""

import sys
import os
from loguru import logger

from config import LOG_CONFIG

_initialized = False


def setup_logger() -> None:
    """
    初始化全局日志配置（幂等操作，多次调用只生效一次）。
    应在应用启动时调用一次。
    """
    global _initialized
    if _initialized:
        return
    _initialized = True

    # 移除默认 handler
    logger.remove()

    # 确保日志目录存在
    log_dir = LOG_CONFIG["log_dir"]
    os.makedirs(log_dir, exist_ok=True)

    # 设置默认 extra 值（未绑定时使用 "unknown"）
    logger.configure(extra={"trace_id": "unknown"})

    # ---- 控制台输出（彩色）----
    logger.add(
        sys.stderr,
        level=LOG_CONFIG["log_level"],
        format=(
            "<green>{time:HH:mm:ss.SSS}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{extra[trace_id]:<12}</cyan> | "
            "<level>{message}</level>"
        ),
        colorize=True,
    )

    # ---- 全量日志文件（按天切割）----
    logger.add(
        os.path.join(log_dir, "smartshop_{time:YYYY-MM-DD}.log"),
        level="DEBUG",
        format=LOG_CONFIG["format"],
        rotation=LOG_CONFIG["rotation"],
        retention=LOG_CONFIG["retention"],
        encoding="utf-8",
    )

    # ---- 错误日志单独文件 ----
    logger.add(
        os.path.join(log_dir, "error_{time:YYYY-MM-DD}.log"),
        level="ERROR",
        format=LOG_CONFIG["format"],
        rotation=LOG_CONFIG["rotation"],
        retention=LOG_CONFIG["retention"],
        encoding="utf-8",
    )

    logger.bind(trace_id="INIT").info("日志系统初始化完成 | 日志目录: {}", os.path.abspath(log_dir))


def get_trace_logger(trace_id: str = "unknown"):
    """
    获取绑定 trace_id 的 logger 实例。
    用法: logger = get_trace_logger(trace_id); logger.info("...")
    """
    return logger.bind(trace_id=trace_id)


# 模块加载时自动初始化
setup_logger()
