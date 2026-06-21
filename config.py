"""
=============================================================================
SmartShop 全局配置文件
=============================================================================
集中管理所有环境参数：数据库、API密钥、服务端口、超时时间等。
部署时请修改本文件中的敏感信息（数据库密码、API Key 等）。
=============================================================================
"""

import os

# ============================================================================
# 1. 大模型配置（DeepSeek API，兼容 OpenAI 接口规范）
# ============================================================================
LLM_CONFIG = {
    "api_base": os.getenv("LLM_API_BASE", "https://api.deepseek.com"),
    "api_key": os.getenv("LLM_API_KEY", "sk-f8a473a3bdc34405a66e3cea8e44b967"),
    "model": os.getenv("LLM_MODEL", "deepseek-chat"),
    "max_tokens": 4096,
    "temperature": 0.1,          # 低温度保证 SQL 生成稳定性
    "request_timeout": 60,       # LLM 请求超时（秒）
}

# ============================================================================
# 2. 数据库配置（MySQL 8.0）
# ============================================================================
MYSQL_CONFIG = {
    "host": os.getenv("MYSQL_HOST", "127.0.0.1"),
    "port": int(os.getenv("MYSQL_PORT", "3306")),
    "user": os.getenv("MYSQL_USER", "root"),
    "password": os.getenv("MYSQL_PASSWORD", "123456"),
    "database": os.getenv("MYSQL_DATABASE", "smartshop"),
    "charset": "utf8mb4",
    "connect_timeout": 10,
    "pool_size": 5,              # 连接池大小
}

# ============================================================================
# 3. MCP 服务端配置
# ============================================================================
MCP_PRODUCT_SERVER = {
    "host": os.getenv("MCP_PRODUCT_HOST", "127.0.0.1"),
    "port": int(os.getenv("MCP_PRODUCT_PORT", "8100")),
    "url": os.getenv("MCP_PRODUCT_URL", "http://127.0.0.1:8100"),
    "sse_url": os.getenv("MCP_PRODUCT_SSE_URL", "http://127.0.0.1:8100/mcp/sse"),
}

MCP_ORDER_SERVER = {
    "host": os.getenv("MCP_ORDER_HOST", "127.0.0.1"),
    "port": int(os.getenv("MCP_ORDER_PORT", "8101")),
    "url": os.getenv("MCP_ORDER_URL", "http://127.0.0.1:8101"),
    "sse_url": os.getenv("MCP_ORDER_SSE_URL", "http://127.0.0.1:8101/mcp/sse"),
}

# ============================================================================
# 4. 商品分类配置
# ============================================================================
PRODUCT_CATEGORIES = {
    "electronics": "数码电子",
    "clothing": "服饰鞋包",
    "food": "食品饮料",
    "beauty": "美妆个护",
    "home": "家居生活",
    "sports": "运动户外",
}

# ============================================================================
# 5. SQL 执行安全配置
# ============================================================================
SQL_SAFE_CONFIG = {
    "max_execution_time": 10,    # SQL 最大执行时间（秒）
    "max_return_rows": 500,      # 最大返回行数
    "allowed_tables": [          # 白名单表
        "product_info",
        "order_info",
    ],
    # 禁止的 SQL 关键字（写操作 / 危险操作）
    "forbidden_keywords": [
        "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE",
        "TRUNCATE", "REPLACE", "LOAD", "GRANT", "REVOKE",
        "EXEC", "EXECUTE", "INTO OUTFILE", "INTO DUMPFILE",
        "BENCHMARK", "SLEEP",
    ],
}

# ============================================================================
# 6. A2A 路由后端配置
# ============================================================================
A2A_ROUTER_SERVER = {
    "host": os.getenv("A2A_ROUTER_HOST", "127.0.0.1"),
    "port": int(os.getenv("A2A_ROUTER_PORT", "8008")),
    "url": os.getenv("A2A_ROUTER_URL", "http://127.0.0.1:8008"),
}

# ============================================================================
# 7. A2A 通信协议配置
# ============================================================================
A2A_CONFIG = {
    "request_timeout": 60,       # 后端调用超时（秒），LLM 推理可能较慢
    "max_retries": 2,            # 失败重试次数
    "retry_delay": 1.0,          # 重试间隔（秒）
}

# ============================================================================
# 8. Streamlit 前端配置
# ============================================================================
STREAMLIT_CONFIG = {
    "page_title": "SmartShop 智能电商导购助手",
    "page_icon": "🛒",
    "layout": "wide",
    "port": int(os.getenv("STREAMLIT_PORT", "8502")),
}

# ============================================================================
# 9. 日志配置
# ============================================================================
LOG_CONFIG = {
    "log_dir": "logs",
    "log_level": "INFO",
    "rotation": "00:00",         # 每天午夜切割
    "retention": "30 days",      # 保留 30 天
    "format": (
            "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | "
            "trace_id={extra[trace_id]} | {name}:{function}:{line} | {message}"
    ),
}

# ============================================================================
# 10. LangGraph 编排配置
# ============================================================================
LANGGRAPH_CONFIG = {
    "checkpoint_db": "data/checkpoints.db",  # SQLite checkpoint 文件路径
    "max_history_messages": 20,               # 会话历史滑动窗口大小
    "summary_trigger_count": 10,              # 触发 LLM 摘要压缩的阈值（预留）
    "recursion_limit": 25,                    # 图递归深度上限
}

# ============================================================================
# 11. MCP 客户端配置（官方 SDK SSE 传输）
# ============================================================================
MCP_CLIENT_CONFIG = {
    "sse_read_timeout": 60,       # SSE 连接读取超时（秒）
    "connection_timeout": 10,     # 初始连接超时（秒）
}

# ============================================================================
# 12. SSE 流式传输配置
# ============================================================================
STREAM_CONFIG = {
    "sse_retry_timeout": 3000,    # 客户端重连间隔（毫秒）
    "ping_interval": 15,          # 心跳间隔（秒）
    "token_polling_interval": 0.015,  # token 队列轮询间隔（秒），~60Hz
}

# ============================================================================
# 13. ReAct 循环配置（v2.1）
# ============================================================================
REACT_CONFIG = {
    "max_iterations": 5,           # ReAct 最大工具调用轮数，超过则强制输出答案
}
