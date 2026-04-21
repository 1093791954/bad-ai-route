# AI-Route

多上游模型 Fallback 反代。对外同时暴露 Anthropic (`/v1/messages`) 和 OpenAI (`/v1/chat/completions`) 协议，按配置的模型顺序依次尝试，任一失败自动切换到下一个。

## 架构

```
Claude Code / OpenAI SDK  ──▶  本地反代 (:18624)  ──▶  newapi (统一上游)
                               ├─ /v1/messages
                               ├─ /v1/chat/completions
                               └─ /ui  (Vue 配置页)
```

关键策略：**首 chunk 缓冲** —— 流式响应在首个有效 token 返回前可无缝切换到下一个模型，避免 CC 任务收到半截响应。

## 安装 & 启动

### 1. 安装 Python 依赖

```bash
pip install -e .
```

### 2. 构建前端

```bash
cd web
npm install
npm run build
cd ..
```

构建产物输出到 `ai_route/static/`，供 FastAPI 直接挂载。

### 3. 启动

```bash
python -m ai_route
```

启动后自动打开浏览器到 `http://127.0.0.1:18624/ui`。

## 使用

1. 在 Web UI 填写上游 `base_url` 和 `api_key`（newapi 的）
2. 点「从上游拉取模型列表」→ 勾选需要的模型 → 拖拽排序（上面优先）
3. 点「保存配置」
4. 在 CC switch 中新建 profile：
   - `ANTHROPIC_BASE_URL=http://127.0.0.1:18624`
   - `ANTHROPIC_API_KEY=dummy`（反代会用自己配置的 key 调上游）

OpenAI 客户端同理，`base_url=http://127.0.0.1:18624/v1`。

## 配置项说明

| 字段 | 说明 |
|---|---|
| `cooldown_seconds` | 模型失败后冷却时长，期间跳过，到期自动恢复 |
| `request_timeout` | 单次上游请求超时（秒） |
| `first_chunk_timeout` | 流式响应等待首个有效 chunk 的超时，超时视为失败并切换 |

## Fallback 触发条件

- HTTP 4xx / 5xx
- 连接/读取超时
- 首 chunk 超时（流式）
- 连接被远端关闭

首 chunk 发出后若流中断，反代会补发错误事件并把该模型加入冷却；此后无法再切换（半截响应已无法撤回）。

## 文件布局

```
ai_route/            Python 后端
├── __main__.py      启动入口（uvicorn + 自动开浏览器）
├── app.py           FastAPI 装配
├── config.py        config.json 读写
├── state.py         冷却追踪
├── upstream.py      httpx 客户端 + 认证头
├── router.py        Fallback 核心
├── anthropic_proxy.py
├── openai_proxy.py
├── admin_api.py     /api/*
└── static/          前端构建产物

web/                 Vue 3 前端源码
config.json          运行时配置（自动创建）
```
