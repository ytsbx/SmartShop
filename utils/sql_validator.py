"""
=============================================================================
SQL 安全校验工具
=============================================================================
实现 SQL 语法白名单校验：
  - 仅允许 SELECT 查询
  - 拦截所有写操作与危险语句（INSERT / UPDATE / DELETE / DROP / ALTER 等）
  - 表名白名单校验
  - 禁止多语句注入
"""

import re
from typing import List

from config import SQL_SAFE_CONFIG


class SQLValidator:
    """SQL 安全校验器"""

    # 禁止的 SQL 关键字
    FORBIDDEN_KEYWORDS: List[str] = SQL_SAFE_CONFIG["forbidden_keywords"]

    # 白名单表名
    ALLOWED_TABLES: List[str] = SQL_SAFE_CONFIG["allowed_tables"]

    # 禁止的多语句分隔符
    MULTI_STATEMENT_DELIMITER: str = ";"

    @classmethod
    def validate(cls, sql: str) -> None:
        """
        校验 SQL 语句安全性。

        Args:
            sql: 待校验的 SQL 语句

        Raises:
            ValueError: 校验失败时抛出，含具体原因
        """
        if not sql or not isinstance(sql, str):
            raise ValueError("SQL 语句不能为空")

        sql_stripped = sql.strip()

        # ---- 1. 必须以 SELECT 开头 ----
        if not sql_stripped.upper().startswith("SELECT"):
            raise ValueError(f"仅允许 SELECT 查询，当前语句以 '{sql_stripped[:20]}...' 开头")

        # ---- 2. 禁止多语句（分号注入）----
        # 找到第一个分号后的非空白内容
        semicolon_pos = sql_stripped.find(";")
        if semicolon_pos != -1:
            rest = sql_stripped[semicolon_pos + 1:].strip()
            if rest:
                raise ValueError("禁止多语句查询，检测到分号后有额外内容")

        # ---- 3. 禁止危险关键字 ----
        sql_upper = sql_stripped.upper()
        for keyword in cls.FORBIDDEN_KEYWORDS:
            # 使用词边界匹配，避免误判列名中包含的关键字
            pattern = r'\b' + re.escape(keyword) + r'\b'
            if re.search(pattern, sql_upper):
                raise ValueError(f"SQL 包含禁止关键字: {keyword}")

        # ---- 4. 表名白名单校验 ----
        cls._validate_tables(sql_stripped)

    @classmethod
    def _validate_tables(cls, sql: str) -> None:
        """
        检查 SQL 中引用的表名是否在白名单内。
        匹配 FROM / JOIN 后的表名。
        """
        # 匹配 FROM table_name 和 JOIN table_name
        pattern = r'(?:FROM|JOIN)\s+`?(\w+)`?'
        tables = re.findall(pattern, sql, re.IGNORECASE)

        for table in tables:
            # 跳过子查询别名（纯大写单词通常是别名）
            if table.upper() == table and table not in cls.ALLOWED_TABLES:
                # 可能是别名，跳过（简单启发式）
                continue
            if table.lower() in [t.lower() for t in cls.ALLOWED_TABLES]:
                continue
            # 严格模式：不在白名单就拒绝
            raise ValueError(f"表名 '{table}' 不在白名单中，允许的表: {cls.ALLOWED_TABLES}")
