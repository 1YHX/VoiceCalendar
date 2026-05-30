# 两天冲刺版任务书：VoiceCalendar MVP

## 一、项目目标

开发一个可演示的语音交互式智能日历工具 MVP。

由于开发时间只有两天，本项目优先保证核心流程跑通：

文本/语音指令 → 自然语言解析 → 创建日程 → 页面展示

第一版不追求功能完整，重点是：

1. 项目能正常启动。
2. 前后端能联调。
3. 能通过自然语言创建日程。
4. 能展示日程列表。
5. 能展示 mock 语音识别流程。
6. README 和 PR 描述完整。
7. commit 记录规范，不能一次性提交。

## 二、项目名称

VoiceCalendar：语音交互式智能日历工具

## 三、技术栈

前端：

* Vue 3
* Vite
* Element Plus
* Axios

后端：

* FastAPI
* SQLite
* SQLAlchemy
* httpx
* python-dotenv
* uvicorn

第三方能力：

* DeepSeek API：用于解析自然语言日程指令
* 七牛云 ASR：本版本先预留接口，实际演示使用 mock ASR

## 四、两天内必须完成的功能

### 1. 文本创建日程

用户输入：

明天下午三点提醒我开会

系统调用 DeepSeek API，解析为：

{
"intent": "create",
"title": "开会",
"start_time": "2026-05-31 15:00:00",
"end_time": "2026-05-31 16:00:00",
"reminder_minutes": 10
}

然后保存到 SQLite，并在前端日程列表中展示。

### 2. 查询日程列表

页面展示所有已创建日程。

字段包括：

* 日程标题
* 开始时间
* 结束时间
* 提醒时间
* 原始输入文本

### 3. 删除日程

每条日程后面有删除按钮，可以手动删除。

自然语言删除可以暂时不做。

### 4. mock 语音识别

前端提供音频上传按钮。

后端 /api/asr 接收音频文件后，在 ASR_MOCK=true 模式下直接返回：

今天晚上八点提醒我提交代码

前端把这个识别文本填入输入框，用户可以点击执行创建日程。

### 5. DeepSeek 解析服务

后端封装 deepseek_service.py。

要求：

* 从 .env 读取 DEEPSEEK_API_KEY
* 调用 DeepSeek API
* 要求模型只返回 JSON
* 对模型返回内容做 JSON 解析
* 如果 DeepSeek 解析失败，返回明确错误提示

### 6. 七牛云接口预留

不要求两天内真实接入七牛云 ASR。

但需要在 asr_service.py 中预留：

* mock_asr()
* qiniu_asr_placeholder()

README 中说明：

当前 MVP 默认使用 ASR_MOCK=true 的 mock 模式，后续可以将 qiniu_asr_placeholder 替换为七牛云真实长语音识别 API 调用。

## 五、必须实现的接口

### POST /api/command

输入自然语言指令，自动解析并创建日程。

请求：

{
"text": "明天下午三点提醒我开会"
}

响应：

{
"success": true,
"message": "日程创建成功",
"parsed": {
"intent": "create",
"title": "开会",
"start_time": "2026-05-31 15:00:00",
"end_time": "2026-05-31 16:00:00",
"reminder_minutes": 10
},
"event": {
"id": 1,
"title": "开会",
"start_time": "2026-05-31 15:00:00",
"end_time": "2026-05-31 16:00:00"
}
}

### GET /api/events

获取所有日程。

### DELETE /api/events/{event_id}

删除指定日程。

### POST /api/asr

上传音频，mock 返回识别文本。

响应：

{
"success": true,
"text": "今天晚上八点提醒我提交代码",
"mock": true
}

## 六、前端页面要求

只做一个主页面即可。

页面包含：

1. 项目标题：VoiceCalendar
2. 文本输入框
3. “执行指令”按钮
4. 音频上传按钮
5. 识别文本展示
6. DeepSeek 解析结果展示
7. 日程列表
8. 删除按钮
9. loading 状态
10. 错误提示

不要做复杂页面，不要做登录，不要做权限系统。

## 七、项目结构

voice-calendar/
├── backend/
│   ├── main.py
│   ├── database.py
│   ├── models.py
│   ├── schemas.py
│   ├── requirements.txt
│   ├── .env.example
│   ├── services/
│   │   ├── deepseek_service.py
│   │   ├── asr_service.py
│   │   └── calendar_service.py
├── frontend/
│   ├── package.json
│   ├── index.html
│   ├── vite.config.js
│   └── src/
│       ├── main.js
│       ├── App.vue
│       └── api/
│           └── calendar.js
├── README.md
├── .gitignore
└── docs/
├── daily-progress.md
└── demo-script.md

## 八、环境变量

backend/.env.example：

DEEPSEEK_API_KEY=your_deepseek_api_key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
ASR_MOCK=true
DATABASE_URL=sqlite:///./voice_calendar.db

QINIU_ACCESS_KEY=your_qiniu_access_key
QINIU_SECRET_KEY=your_qiniu_secret_key
QINIU_BUCKET=your_bucket_name
QINIU_REGION=your_region

## 九、DeepSeek Prompt

系统提示词：

你是一个中文日历助手。请把用户的自然语言日程指令解析为严格 JSON。
当前时间由后端传入。
你只需要处理创建日程的指令。
如果用户表达的是查询、删除、修改或无法识别，请返回对应 intent，但不要执行创建。
必须只输出 JSON，不要 Markdown，不要解释。

输出格式：

{
"intent": "create | query | delete | update | unknown | need_clarification",
"title": "",
"description": "",
"start_time": "",
"end_time": "",
"reminder_minutes": 10,
"confidence": 0.0,
"clarification_question": ""
}

规则：

1. 相对时间必须基于后端传入的当前时间解析。
2. 如果没有结束时间，默认持续 1 小时。
3. 如果没有提醒时间，默认提前 10 分钟。
4. 如果缺少具体时间，返回 need_clarification。
5. 只输出 JSON。

## 十、两天开发计划

### Day 1：先跑通后端和核心逻辑

必须完成：

1. 初始化项目结构。
2. 搭建 FastAPI 后端。
3. 搭建 SQLite 数据库。
4. 实现 Event 模型。
5. 实现 GET /api/events。
6. 实现 DELETE /api/events/{event_id}。
7. 实现 DeepSeek 解析服务。
8. 实现 POST /api/command。
9. 用 Postman 或 curl 测试后端接口。

Day 1 推荐 commit：

* feat: initialize voice calendar project
* feat: add fastapi backend structure
* feat: implement event model and database
* feat: implement event list and delete api
* feat: add deepseek calendar parser
* feat: implement command create event api

### Day 2：完成前端、mock 语音和文档

必须完成：

1. 初始化 Vue3 前端。
2. 完成文本输入框。
3. 完成执行指令按钮。
4. 完成日程列表展示。
5. 完成删除按钮。
6. 完成 POST /api/asr mock 接口。
7. 完成音频上传组件。
8. 完成 README。
9. 完成 demo-script.md。
10. 修复前后端联调问题。

Day 2 推荐 commit：

* feat: add vue frontend project
* feat: implement command input page
* feat: display calendar event list
* feat: add event delete interaction
* feat: implement mock asr upload
* docs: add readme and demo script
* style: polish final demo page

## 十一、PR 和提交规范

不要一次性提交所有代码。

每完成一个小模块就提醒我 commit。

commit message 必须使用：

* feat:
* fix:
* docs:
* style:
* refactor:
* chore:

禁止使用：

* update
* test
* 111
* final
* 修改
* bug fix

PR 标题：

[第二批次-题目一] VoiceCalendar：语音交互式智能日历工具

PR 描述：

## 项目简介

VoiceCalendar 是一个语音交互式智能日历工具，支持用户通过自然语言文本或语音输入创建日程。系统使用 DeepSeek API 解析中文日程指令，并使用 SQLite 保存日程数据。语音识别部分当前采用 mock 模式，同时预留七牛云 ASR 接口。

## 已完成功能

* 文本输入创建日程
* DeepSeek 自然语言解析
* SQLite 日程存储
* 日程列表展示
* 日程删除
* mock 语音识别
* 七牛云 ASR 接口预留
* README 和 demo 脚本

## Demo 流程

1. 输入“明天下午三点提醒我开会”。
2. 系统自动解析标题和时间。
3. 创建日程并展示在列表中。
4. 上传音频文件。
5. mock ASR 返回“今天晚上八点提醒我提交代码”。
6. 再次执行创建日程。
7. 删除某条日程。

## 后续优化

* 接入真实七牛云语音识别 API
* 支持浏览器实时录音
* 支持自然语言查询和删除
* 支持日历视图
* 支持提醒通知

## 十二、Codex 执行要求

请严格按照两天 MVP 方案开发。

不要做登录、权限、多用户、复杂日历视图、Google Calendar 同步等功能。

优先保证项目可运行、可演示。

每完成一个阶段，请停下来告诉我：

1. 完成了什么。
2. 我需要执行什么命令。
3. 推荐使用什么 commit message。
4. 下一步做什么。
