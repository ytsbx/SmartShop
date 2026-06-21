"""
=============================================================================
数据库连接封装
=============================================================================
基于 PyMySQL + DBUtils 连接池，提供线程安全的数据库操作。
所有 SQL 执行必须携带 trace_id，用于全链路日志追踪。
"""

import pymysql
from dbutils.pooled_db import PooledDB
from contextlib import contextmanager
from datetime import date, datetime, time
from decimal import Decimal
from typing import Optional, List, Dict, Any
from loguru import logger

from config import MYSQL_CONFIG
from utils.sql_validator import SQLValidator


def _json_serialize_value(val: Any) -> Any:
    """
    将 Python 原生类型转为 JSON 可序列化的值。

    MySQL 驱动返回的 date / datetime / Decimal 等类型无法直接被 json.dumps 处理，
    需要在入库到返回结果之前统一转换。
    """
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(val, date):
        return val.strftime("%Y-%m-%d")
    if isinstance(val, time):
        return val.strftime("%H:%M:%S")
    if isinstance(val, Decimal):
        return float(val)
    if isinstance(val, bytes):
        return val.decode("utf-8", errors="replace")
    return val


def _serialize_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """将整行数据的每个字段转为 JSON 安全类型"""
    return {key: _json_serialize_value(val) for key, val in row.items()}


class MySQLPool:
    """MySQL 连接池（单例模式）"""

    _instance: Optional["MySQLPool"] = None
    _pool: Optional[PooledDB] = None

    def __new__(cls) -> "MySQLPool":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def _get_pool(self) -> PooledDB:
        if self._pool is None:
            try:
                self._pool = PooledDB(
                    creator=pymysql,
                    maxconnections=MYSQL_CONFIG.get("pool_size", 5),
                    mincached=1,
                    blocking=True,
                    host=MYSQL_CONFIG["host"],
                    port=MYSQL_CONFIG["port"],
                    user=MYSQL_CONFIG["user"],
                    password=MYSQL_CONFIG["password"],
                    database=MYSQL_CONFIG["database"],
                    charset=MYSQL_CONFIG["charset"],
                    connect_timeout=MYSQL_CONFIG["connect_timeout"],
                    cursorclass=pymysql.cursors.DictCursor,
                )
                logger.info("MySQL 连接池初始化成功: {}:{}", MYSQL_CONFIG["host"], MYSQL_CONFIG["port"])
            except Exception as e:
                logger.error("MySQL 连接池初始化失败: {}", str(e))
                raise
        return self._pool

    @contextmanager
    def get_connection(self):
        """获取数据库连接（上下文管理器，自动归还）"""
        conn = None
        try:
            conn = self._get_pool().connection()
            yield conn
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error("数据库连接异常: {}", str(e))
            raise
        finally:
            if conn:
                conn.close()


# 全局连接池实例
db_pool = MySQLPool()


def execute_query(
    sql: str,
    params: Optional[tuple] = None,
    trace_id: str = "unknown",
    max_rows: int = 500,
    timeout: int = 10,
) -> List[Dict[str, Any]]:
    """
    安全执行 SELECT 查询（参数化查询，防注入）。

    Args:
        sql:    SQL 语句（仅允许 SELECT）
        params: 参数元组
        trace_id: 全链路追踪 ID
        max_rows: 最大返回行数
        timeout: 执行超时（秒）

    Returns:
        查询结果列表 [{"col": val, ...}, ...]

    Raises:
        ValueError: SQL 未通过安全校验
        RuntimeError: 数据库执行异常
    """
    # 1. SQL 安全校验
    SQLValidator.validate(sql)

    # 2. 参数校验
    if params is not None and not isinstance(params, (tuple, list)):
        raise ValueError(f"SQL 参数必须为 tuple/list 类型，实际: {type(params)}")

    logger.info("[{}] 执行查询 | SQL: {} | params: {}", trace_id, sql[:200], params)

    try:
        with db_pool.get_connection() as conn:
            with conn.cursor() as cursor:
                # 设置查询超时
                cursor.execute(f"SET SESSION max_execution_time={timeout * 1000}")
                cursor.execute(sql, params)

                # 限制返回行数
                rows = cursor.fetchmany(max_rows)
                # 将 date/datetime/Decimal 等转为 JSON 安全类型，防止序列化 500
                result = [_serialize_row(dict(row)) for row in rows]

                logger.info("[{}] 查询完成 | 返回 {} 行", trace_id, len(result))
                return result

    except pymysql.Error as e:
        logger.error("[{}] 数据库查询异常: {}", trace_id, str(e))
        raise RuntimeError(f"数据库查询失败: {e}") from e
    except Exception as e:
        logger.error("[{}] 未知查询异常: {}", trace_id, str(e))
        raise
