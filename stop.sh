#!/bin/bash
# ============================================================================
# SmartShop — 一键停止所有服务
# ============================================================================

echo "=== 正在停止 SmartShop 全部服务 ==="

# 按端口 kill
for port in 8502 8008 8101 8100; do
    if lsof -i :$port -t &>/dev/null 2>&1; then
        echo "[停止] 端口 $port..."
        lsof -i :$port -t | xargs kill -9 2>/dev/null || true
    else
        echo "[跳过] 端口 $port 无进程"
    fi
done

echo "=== SmartShop 已全部停止 ==="
