# ============================================================================
# SmartShop v2.0 — Docker 镜像
# ============================================================================
FROM python:3.11-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    default-mysql-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制源码
COPY . .

# 默认命令（由 docker-compose 覆盖）
CMD ["python", "-m", "uvicorn", "core.router_A2Aagent_Server:app", "--host", "0.0.0.0", "--port", "8008"]
