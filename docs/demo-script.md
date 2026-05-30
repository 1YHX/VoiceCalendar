# VoiceCalendar Demo Script

## 准备

1. 启动后端：

```bash
conda activate voice-calendar
cd backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

2. 启动前端：

```bash
cd frontend
npm run dev
```

3. 打开：

```text
http://localhost:5173
```

## 演示流程

1. 展示页面标题 `VoiceCalendar`、文本输入框、上传音频按钮和日程列表。
2. 输入 `明天下午三点提醒我开会`。
3. 点击“执行指令”。
4. 展示解析结果：

```json
{
  "intent": "create",
  "title": "开会",
  "start_time": "2026-05-31 15:00:00",
  "end_time": "2026-05-31 16:00:00",
  "reminder_minutes": 10
}
```

5. 确认日程列表新增“开会”。
6. 点击“开始语音输入”，授权麦克风后说一句话。
7. 点击“停止录音”，展示 ASR 返回文本；mock 模式下返回 `今天晚上八点提醒我提交代码`。
8. 点击“执行指令”，确认新增“提交代码”。
9. 点击删除按钮，确认对应日程从列表移除。

## 说明

- 当前 MVP 默认 `ASR_MOCK=true`，录音文件不会调用真实语音识别。
- 设置 `ASR_MOCK=false` 并配置腾讯云密钥后，后端会调用腾讯云一句话识别。
- 如果没有配置真实 `DEEPSEEK_API_KEY`，后端会用本地兜底解析支持演示指令。
