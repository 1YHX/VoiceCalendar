# VoiceCalendar

VoiceCalendar 是一个语音交互式智能日历工具 MVP，支持通过中文自然语言文本或麦克风录音创建日程。

## 已完成功能

- 文本输入创建日程
- DeepSeek 自然语言解析封装
- SQLite 日程存储
- 日程列表展示
- 日程删除
- 浏览器麦克风录音并上传识别
- 七牛云短语音听写接口接入
- mock ASR 模式保留，便于接口权限未开通时演示

## 技术栈

- 前端：Vue 3、Vite、Element Plus、Axios
- 后端：FastAPI、SQLite、SQLAlchemy、httpx、python-dotenv、uvicorn
- 第三方能力：DeepSeek API、七牛云短语音听写

## 项目结构

```text
backend/
  main.py
  database.py
  models.py
  schemas.py
  requirements.txt
  .env.example
  services/
    deepseek_service.py
    asr_service.py
    calendar_service.py
frontend/
  package.json
  index.html
  vite.config.js
  src/
    main.js
    App.vue
    api/calendar.js
docs/
  daily-progress.md
  demo-script.md
```

## 后端启动

```bash
conda create -n voice-calendar python=3.11 -y
conda activate voice-calendar
cd backend
pip install -r requirements.txt
cp .env.example .env
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

`.env` 中配置真实 DeepSeek API Key 后会调用 DeepSeek。未配置真实 Key 时，后端会使用本地 MVP 兜底解析，以便演示任务书中的典型指令。

ASR 支持两种模式：

```env
ASR_MOCK=true
```

`ASR_MOCK=true` 时走 mock，`ASR_MOCK=false` 时走真实七牛短语音听写接口。

如果要使用七牛云短语音听写，把 `.env` 改为：

```env
ASR_MOCK=false
QINIU_ACCESS_KEY=你的 AccessKey
QINIU_SECRET_KEY=你的 SecretKey
QINIU_ASR_URL=http://yitu-audio.qiniuapi.com/v2/asr
QINIU_BUCKET=
QINIU_REGION=
```

当前实现会把浏览器录音编码为 WAV，上传到后端后转为 `audioDataBase64` 请求七牛短语音听写接口，不依赖 bucket 和 region。

注意：七牛短语音听写需要账号侧开通接口权限。权限未开通时接口可能返回 403，此时可临时使用 `ASR_MOCK=true` 保证 demo 流程可跑通。

## 前端启动

```bash
cd frontend
npm install
npm run dev
```

浏览器访问：

```text
http://localhost:5173
```

## Demo 流程

1. 启动后端和前端。
2. 在输入框输入 `明天下午三点提醒我开会`。
3. 点击“执行指令”。
4. 页面展示解析结果，并在日程列表展示新日程。
5. 点击“开始语音输入”，授权麦克风后说一句话。
6. 点击“停止录音”，系统上传录音并通过 ASR 返回识别文本。
7. 再次点击“执行指令”创建第二条日程。
8. 点击删除按钮删除某条日程。

## API

### POST /api/command

```json
{
  "text": "明天下午三点提醒我开会"
}
```

### GET /api/events

获取所有日程。

### DELETE /api/events/{event_id}

删除指定日程。

### POST /api/asr

上传音频文件。`ASR_MOCK=true` 时返回 mock 识别文本，`ASR_MOCK=false` 时调用七牛短语音听写。

## PR 描述

标题：

```text
[第二批次-题目一] VoiceCalendar：语音交互式智能日历工具
```

描述：

```markdown
## 项目简介

VoiceCalendar 是一个语音交互式智能日历工具，支持用户通过自然语言文本或语音输入创建日程。系统使用 DeepSeek API 解析中文日程指令，并使用 SQLite 保存日程数据。语音识别部分已接入七牛云短语音听写，同时保留 mock 模式便于演示。

## 已完成功能

* 文本输入创建日程
* DeepSeek 自然语言解析
* SQLite 日程存储
* 日程列表展示
* 日程删除
* 浏览器麦克风录音
* 七牛云短语音听写接口接入
* mock ASR 模式保留
* README 和 demo 脚本

## Demo 流程

1. 输入“明天下午三点提醒我开会”。
2. 系统自动解析标题和时间。
3. 创建日程并展示在列表中。
4. 点击“开始语音输入”，录制一段语音后停止。
5. ASR 返回识别文本并填入输入框。
6. 再次执行创建日程。
7. 删除某条日程。

## 后续优化

* 等待七牛云短语音听写权限开通并完成真实环境验证
* 支持浏览器实时流式识别
* 支持自然语言查询和删除
* 支持日历视图
* 支持提醒通知
```
