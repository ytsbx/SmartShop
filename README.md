# 🛒 SmartShop 智能电商导购助手 v2.0

基于 **LangGraph + FastMCP + SSE 流式输出** 的 Multi-Agent 智能电商导购系统。用户用自然语言一句话描述需求，系统自动拆解为商品搜索/订单查询子任务，并发执行后汇总回答。

---

## ✨ 核心特性

- **自然语言交互** — "推荐一款蓝牙耳机，预算500以内" → 自动搜索 + 比价 + 推荐
- **Multi-Agent 并行** — 复杂查询自动拆解，商品 Agent + 订单 Agent 并发执行
- **MCP 协议微服务** — 商品 / 订单各自独立 MCP Server，可独立部署和扩展
- **SSE 流式输出** — 实时推送查询进度和中间结果
- **多轮对话** — 上下文记忆，支持 "有便宜的吗""换一个品牌" 等追问
- **结构化数据展示** — 搜索结果以表格呈现，支持展开查看详情

---

## 🏗️ 系统架构

```
┌──────────────┐     HTTP/SSE      ┌──────────────────┐     MCP over SSE     ┌───────────────┐
│  Streamlit   │ ◄──────────────► │  A2A Router       │ ◄──────────────────► │ Product MCP   │
│  前端 :8502  │                   │  (LangGraph) :8008│                      │ Server :8100  │
└──────────────┘                   │                    │                      └───────┬───────┘
                                   │  ┌──────────────┐ │                              │
                                   │  │ decompose    │ │                      ┌───────┴───────┐
                                   │  │   query      │ │                      │ Order MCP     │
                                   │  └──────┬───────┘ │                      │ Server :8101  │
                                   │         │          │                      └───────┬───────┘
                                   │  ┌──────┴───────┐ │                              │
                                   │  │ Send fan-out │ │                      ┌───────┴───────┐
                                   │  └──┬───────┬───┘ │                      │    MySQL      │
                                   │     │       │     │                      │   :3306      │
                                   │  ┌──▼──┐ ┌──▼──┐ │                      └───────────────┘
                                   │  │Prod │ │Order│ │
                                   │  │Agent│ │Agent│ │
                                   │  └──┬──┘ └──┬──┘ │
                                   │     │       │     │
                                   │  ┌──▼───────▼──┐ │
                                   │  │  aggregate  │ │
                                   │  └─────────────┘ │
                                   └──────────────────┘
```

**数据流**：用户输入 → decompose_query (LLM拆解) → route → Send fan-out 到 ProductAgent + OrderAgent → 各自通过 MCP 协议调 MCP Server → 查 MySQL → aggregate_node (LLM汇总) → SSE 流式返回前端

---

## 🚀 快速开始

### 环境要求

- Python 3.10+
- MySQL 8.0+
- DeepSeek API Key（或其他 OpenAI 兼容接口）

### 安装

```bash
git clone <repo-url>
cd SmartShop

python -m venv .venv
source .venv/bin/activate   # Linux/Mac
# .venv\Scripts\activate    # Windows

pip install -r requirements.txt
```

### 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填入你的 LLM_API_KEY 和数据库密码
```

### 初始化数据库

```bash
# 创建数据库和表
mysql -u root -p < sql/init_shop.sql

# 生成模拟数据（60+ 商品 + 100+ 订单）
python data/product_mock.py
python data/order_mock.py
```

### 启动

```bash
# 一键启动（4 个服务窗口）
./start.sh    # Linux/Mac/Git Bash
# 或
start.bat     # Windows

# 或者手动依次启动：
# 终端1: python -m uvicorn mcp_servers.mcp_product_server:app --host 127.0.0.1 --port 8100
# 终端2: python -m uvicorn mcp_servers.mcp_order_server:app --host 127.0.0.1 --port 8101
# 终端3: python -m uvicorn core.router_A2Aagent_Server:app --host 127.0.0.1 --port 8008
# 终端4: streamlit run main.py
```

访问 **http://localhost:8502** 开始使用。

---

## 📂 项目结构

```
SmartShop/
├── main.py                          # Streamlit 前端入口
├── config.py                        # 全局配置（LLM / MySQL / MCP / 端口）
├── requirements.txt                 # Python 依赖
├── Dockerfile                       # Docker 镜像
├── docker-compose.yml               # Docker Compose 部署
├── start.sh / start.bat             # 一键启动脚本
├── stop.sh  / stop.bat              # 一键停止脚本
│
├── core/                            # 核心内核（领域无关）
│   ├── graph.py                     # LangGraph 图组装
│   ├── graph_nodes.py               # 图节点函数（decompose / agent / aggregate）
│   ├── state.py                     # MainState 状态定义
│   ├── router_A2Aagent_Server.py    # A2A Router Server (FastAPI + SSE)
│   ├── mcp_client.py                # 通用 MCP 客户端（SSE 传输）
│   ├── llm_utils.py                 # LLM 调用封装
│   ├── prompt_loader.py             # Prompt 模板加载器
│   ├── logger.py                    # 日志系统
│   └── memory_manager.py            # 会话记忆裁剪
│
├── agents/                          # 领域 Agent（LLM 参数提取 + MCP 调用 + 结果摘要）
│   ├── product_agent_client.py      # 商品 Agent
│   └── order_agent_client.py        # 订单 Agent
│
├── mcp_servers/                     # MCP 服务端（FastMCP + FastAPI）
│   ├── mcp_product_server.py        # 商品 MCP Server（query_product）
│   └── mcp_order_server.py          # 订单 MCP Server（query_order）
│
├── data/                            # 数据层
│   ├── mysql_conn.py                # MySQL 连接池 + 安全查询
│   ├── product_mock.py              # 商品模拟数据生成器
│   └── order_mock.py                # 订单模拟数据生成器
│
├── prompts/                         # Prompt 模板
│   ├── decompose.txt                # 查询分解模板
│   ├── aggregate.txt                # 结果聚合模板
│   ├── product_extract.txt          # 商品参数提取模板
│   └── order_extract.txt            # 订单参数提取模板
│
├── sql/
│   └── init_shop.sql                # SmartShop 数据库建表脚本
│
└── utils/
    └── sql_validator.py             # SQL 安全校验器
```

---

## 🛠️ API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/chat` | 同步聊天接口 |
| GET | `/api/chat/stream` | SSE 流式聊天接口 |
| GET | `/api/health` | 健康检查（含下游 MCP 探测） |
| GET | `/api/services` | 下游服务列表 |
| GET | `/docs` | FastAPI 自动生成的 API 文档 |

---

## 🎯 支持的查询类型

### 商品查询
- "推荐一款蓝牙耳机" → 关键词搜索
- "500 以内的机械键盘" → 价格筛选
- "小米的产品" → 品牌筛选
- "评分最高的运动装备" → 分类 + 排序
- "有什么好吃的零食" → 分类浏览

### 订单查询
- "我的订单到哪了" → 客户订单 + 物流追踪
- "最近一周的订单" → 日期范围筛选
- "有没有退款的" → 状态筛选
- "ORD20260619001" → 订单号精确查询

### 复合查询
- "帮我推荐一款性价比高的机械键盘，顺便查下我最近的订单" → 自动拆解为 2 个子任务并行执行
- "最近买了哪些数码产品" → 分类 + 订单联合

### 多轮对话
- 先问"推荐蓝牙耳机" → 追问"有便宜一点的吗？" → 上下文继承

---

## 🔧 技术栈

| 层 | 技术 | 说明 |
|----|------|------|
| 前端交互 | Streamlit | 聊天界面 + SSE 消费 |
| 后端编排 | FastAPI + LangGraph | A2A Router + 图编排 + Checkpoint |
| Agent 框架 | 自定义 Agent | LLM 参数提取 → MCP 调用 → 结果摘要 |
| 服务协议 | MCP (Model Context Protocol) | Agent 与工具服务之间的标准通信 |
| MCP 传输 | FastMCP + SSE | 官方 MCP SDK 的 SSE 传输模式 |
| LLM | DeepSeek (OpenAI 兼容) | 查询分解 / 参数提取 / 结果聚合 |
| 数据库 | MySQL 8.0 | 商品 / 订单数据存储 |
| 容器化 | Docker + Compose | 一键部署全部 6 个服务 |

---

## 📊 MCP 工具清单

### Product MCP Server (`:8100`)
| 工具 | 参数 | 说明 |
|------|------|------|
| `query_product` | category, keyword, brand, min_price, max_price, min_rating, sort_by, limit | 多维度商品搜索与筛选 |
| `ping` | - | 健康检查 |

### Order MCP Server (`:8101`)
| 工具 | 参数 | 说明 |
|------|------|------|
| `query_order` | order_no, customer_name, status, order_date_from, order_date_to, limit | 多维度订单查询 |
| `ping` | - | 健康检查 |

---

## 🐳 Docker Compose 部署

```bash
# 启动全部服务
docker compose up -d

# 初始化模拟数据
docker compose --profile init up init-data

# 查看日志
docker compose logs -f

# 停止
docker compose down
```

---

---

## 📄 License

MIT
