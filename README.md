# VoiceCalendar

VoiceCalendar 是一个语音交互式智能日历工具，支持通过中文自然语言文本或麦克风录音管理日程。前端只负责录音和提交文本；后端会把用户指令和当前本地日程上下文一起交给 DeepSeek，由 DeepSeek 解析添加、查看、删除等操作后再执行。

## 已完成功能

- 文本或语音指令创建日程
- 文本或语音指令查看日程
- 文本或语音指令删除日程
- DeepSeek 自然语言解析封装
- SQLite 日程存储
- 日历和日程列表展示
- 月历展示农历和节日
- 浏览器本地日程提醒
- DeepSeek 提醒文案生成和腾讯云 TTS 语音提醒
- 创建、查询、删除等操作结果语音播报，TTS 不可用时自动使用浏览器语音兜底
- 浏览器麦克风录音并上传识别
- 腾讯云一句话识别接口接入
- mock ASR 模式保留，便于本地演示

## 技术栈

- 前端：Vue 3、Vite、Element Plus、Axios
- 后端：FastAPI、SQLite、SQLAlchemy、httpx、python-dotenv、uvicorn
- 第三方能力：DeepSeek API、腾讯云语音识别

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

`.env` 中配置真实 DeepSeek API Key 后会调用 DeepSeek。未配置真实 Key 时，后端会使用本地兜底解析，以便演示任务书中的典型指令。

ASR 支持两种模式：

```env
ASR_MOCK=true
```

`ASR_MOCK=true` 时走 mock，`ASR_MOCK=false` 时走真实腾讯云一句话识别接口。

如果要使用腾讯云语音识别，把 `.env` 改为：

```env
ASR_MOCK=false
TENCENT_SECRET_ID=你的 SecretId
TENCENT_SECRET_KEY=你的 SecretKey
TENCENT_ASR_REGION=ap-shanghai
TENCENT_ASR_ENDPOINT=asr.tencentcloudapi.com
TENCENT_ASR_ENGINE=16k_zh
TENCENT_TTS_REGION=ap-shanghai
TENCENT_TTS_ENDPOINT=tts.tencentcloudapi.com
TENCENT_TTS_VOICE_TYPE=101001
TENCENT_TTS_CODEC=wav
TENCENT_TTS_SAMPLE_RATE=16000
```

当前实现会把浏览器录音编码为 WAV，上传到后端后转为 base64，请求腾讯云 `SentenceRecognition` 一句话识别接口。
提醒触发时，后端会先调用 DeepSeek 生成一句提醒文案，再调用腾讯云 `TextToVoice` 合成语音并由前端播放。创建、查询、删除等操作结果也会请求 TTS 播报；如果腾讯云 TTS 额度不足或调用失败，前端会自动使用浏览器本地语音兜底。

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
4. 页面展示解析结果，并在日历和日程列表展示新日程。
5. 点击“开始语音指令”，授权麦克风后说一句话。
6. 点击“停止录音”，系统上传录音并通过 ASR 返回识别文本，然后自动执行添加、查看或删除。
7. 输入或说出 `查看明天日程`，页面展示查询结果。
8. 输入或说出 `删除开会`，系统删除匹配的日程。
9. 点击“开启提醒”，允许浏览器通知后等待提醒时间触发。

## API

### POST /api/command

统一的自然语言日历指令入口。后端会把文本和当前日程列表交给 DeepSeek 解析为结构化意图，再执行创建、查询或删除。

```json
{
  "text": "明天下午三点提醒我开会"
}
```

也支持：

```json
{
  "text": "显示所有日程计划"
}
```

```json
{
  "text": "删除开会"
}
```

### GET /api/events

获取所有日程。

### DELETE /api/events/{event_id}

删除指定日程。

### POST /api/asr

上传音频文件。`ASR_MOCK=true` 时返回 mock 识别文本，`ASR_MOCK=false` 时调用腾讯云一句话识别。

### POST /api/reminder-speech

根据日程信息生成语音提醒。后端先用 DeepSeek 生成播报文案，再调用腾讯云 TTS 返回音频。

### POST /api/speech

把普通操作反馈文本合成为语音，用于创建、查询、删除等操作结果播报。前端在该接口失败时使用浏览器本地语音兜底。

## PR 描述

标题：

```text
[第二批次-题目一] VoiceCalendar：语音交互式智能日历工具
```

描述：

```markdown
## 项目简介

VoiceCalendar 是一个语音交互式智能日历工具，支持用户通过自然语言文本或语音输入添加、查看、删除日程。系统使用 DeepSeek API 解析中文日历管理指令，并使用 SQLite 保存日程数据。语音识别部分已接入腾讯云一句话识别，同时保留 mock 模式便于演示。

## 已完成功能

* 文本或语音指令创建日程
* 文本或语音指令查看日程
* 文本或语音指令删除日程
* DeepSeek 自然语言解析
* SQLite 日程存储
* 月历和日程列表展示
* 农历和节日展示
* 浏览器本地提醒通知
* DeepSeek 提醒文案生成和腾讯云 TTS 语音提醒
* 创建、查询、删除等操作结果语音播报
* 浏览器麦克风录音
* 腾讯云一句话识别接口接入
* mock ASR 模式保留
* README 和 demo 脚本

## Demo 流程

1. 输入或说出“明天下午三点提醒我开会”。
2. 系统自动解析标题和时间。
3. 创建日程并展示在日历和列表中。
4. 点击“开始语音指令”，录制一段语音后停止。
5. ASR 返回识别文本并自动执行日历操作。
6. 说出“查看明天日程”，系统展示查询结果。
7. 说出“删除开会”，系统删除匹配日程。
8. 系统对创建、查询、删除结果进行语音播报。
9. 开启提醒通知，等待日程提醒触发。

## 后续优化

* 完成腾讯云语音识别真实环境验证和错误处理优化
* 支持浏览器实时流式识别
* 支持更精确的多条件查询和删除确认
* 支持服务端持久提醒任务
```
