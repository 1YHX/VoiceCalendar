<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import {
  ArrowLeft,
  ArrowRight,
  Bell,
  Delete,
  Microphone,
  Refresh,
  VideoPause,
  VideoPlay
} from '@element-plus/icons-vue'
import { ElMessage, ElNotification } from 'element-plus'
import { Solar } from 'lunar-javascript'
import {
  createReminderSpeech,
  createSpeech,
  deleteEvent,
  executeCalendarCommand,
  getEvents,
  uploadAudio
} from './api/calendar'

const commandText = ref('明天下午三点提醒我开会')
const recognizedText = ref('')
const parsed = ref(null)
const commandResults = ref([])
const hasQueryResult = ref(false)
const lastCommandText = ref('')
const lastExecutionMessage = ref('')
const lastMatchedEvents = ref([])
const events = ref([])
const loading = ref(false)
const listLoading = ref(false)
const asrLoading = ref(false)
const recording = ref(false)
const errorMessage = ref('')
const voiceStatus = ref('')
const calendarCursor = ref(new Date())
const notificationPermission = ref('unsupported')
let audioContext = null
let audioSource = null
let audioProcessor = null
let micStream = null
let recordingBuffers = []
let recordingSampleRate = 44100
let reminderTimers = new Map()
let activeSpeech = null
const TENCENT_ASR_SAMPLE_RATE = 16000
const REMINDED_STORAGE_KEY = 'voice-calendar-reminded-ids'
const IMMEDIATE_REMINDER_DELAY_MS = 4000

function formatTime(value) {
  if (!value) return '-'
  return value.replace('T', ' ').slice(0, 19)
}

function formatClock(value) {
  if (!value) return '--:--'
  return value.replace('T', ' ').slice(11, 16)
}

function formatReminder(row) {
  const reminderAt = getReminderAt(row)
  if (!reminderAt) return '-'
  return formatTime(toLocalDateTimeString(reminderAt))
}

function dateKey(value) {
  return value.replace('T', ' ').slice(0, 10)
}

function parseLocalDateTime(value) {
  if (!value) return null
  const normalized = value.replace('T', ' ').slice(0, 19)
  const [datePart, timePart = '00:00:00'] = normalized.split(' ')
  const [year, month, day] = datePart.split('-').map(Number)
  const [hour = 0, minute = 0, second = 0] = timePart.split(':').map(Number)
  if (!year || !month || !day) return null
  return new Date(year, month - 1, day, hour, minute, second)
}

function toLocalDateTimeString(date) {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  const hour = String(date.getHours()).padStart(2, '0')
  const minute = String(date.getMinutes()).padStart(2, '0')
  const second = String(date.getSeconds()).padStart(2, '0')
  return `${year}-${month}-${day} ${hour}:${minute}:${second}`
}

function getReminderAt(event) {
  const start = parseLocalDateTime(event.start_time)
  if (!start) return null
  return new Date(start.getTime() - event.reminder_minutes * 60 * 1000)
}

function toLocalDateKey(date) {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function getLunarInfo(date) {
  // 月历只在展示层计算农历和节日，不影响后端日程数据结构。
  const solar = Solar.fromYmd(date.getFullYear(), date.getMonth() + 1, date.getDate())
  const lunar = solar.getLunar()
  const solarFestivals = solar.getFestivals()
  const lunarFestivals = lunar.getFestivals()
  const jieQi = lunar.getJieQi()
  const festival = [...solarFestivals, ...lunarFestivals, jieQi].filter(Boolean)[0] || ''
  const lunarDay = lunar.getDay() === 1 ? `${lunar.getMonthInChinese()}月` : lunar.getDayInChinese()

  return {
    lunarText: festival || lunarDay,
    festival,
  }
}

const calendarTitle = computed(() => {
  const date = calendarCursor.value
  return `${date.getFullYear()} 年 ${date.getMonth() + 1} 月`
})

const agentDecisionSteps = computed(() => {
  if (!parsed.value && !lastExecutionMessage.value) return []
  const matched = lastMatchedEvents.value.length
    ? lastMatchedEvents.value.map((event) => event.title).join('、')
    : '无'
  return [
    { label: '用户指令', value: lastCommandText.value || commandText.value || '-' },
    { label: 'DeepSeek 意图', value: parsed.value?.intent || '-' },
    { label: '匹配日程', value: matched },
    { label: '执行结果', value: lastExecutionMessage.value || '-' },
  ]
})

const monthCells = computed(() => {
  const cursor = calendarCursor.value
  const year = cursor.getFullYear()
  const month = cursor.getMonth()
  const firstDay = new Date(year, month, 1)
  const start = new Date(firstDay)
  start.setDate(firstDay.getDate() - firstDay.getDay())

  return Array.from({ length: 42 }, (_, index) => {
    const date = new Date(start)
    date.setDate(start.getDate() + index)
    const key = toLocalDateKey(date)
    const lunarInfo = getLunarInfo(date)
    return {
      key,
      day: date.getDate(),
      lunarText: lunarInfo.lunarText,
      festival: lunarInfo.festival,
      currentMonth: date.getMonth() === month,
      today: key === toLocalDateKey(new Date()),
      events: events.value.filter((event) => dateKey(event.start_time) === key)
    }
  })
})

function changeMonth(offset) {
  const next = new Date(calendarCursor.value)
  next.setMonth(next.getMonth() + offset)
  calendarCursor.value = next
}

function backToToday() {
  calendarCursor.value = new Date()
}

function getReminderKey(event) {
  return [event.id, event.title, event.start_time, event.reminder_minutes].join('|')
}

function getRemindedKeys() {
  try {
    return new Set(JSON.parse(localStorage.getItem(REMINDED_STORAGE_KEY) || '[]'))
  } catch {
    return new Set()
  }
}

function markReminded(event) {
  const keys = getRemindedKeys()
  keys.add(getReminderKey(event))
  localStorage.setItem(REMINDED_STORAGE_KEY, JSON.stringify([...keys]))
}

function clearReminderState(event) {
  const key = getReminderKey(event)
  const keys = getRemindedKeys()
  keys.delete(key)
  localStorage.setItem(REMINDED_STORAGE_KEY, JSON.stringify([...keys]))
  if (reminderTimers.has(key)) {
    clearTimeout(reminderTimers.get(key))
    reminderTimers.delete(key)
  }
}

async function playReminderSpeech(event) {
  try {
    const { data } = await createReminderSpeech(event)
    const audio = new Audio(`data:${data.audio_mime};base64,${data.audio_base64}`)
    await audio.play()
  } catch (error) {
    const fallback = `日程提醒，${formatClock(event.start_time)}，${event.title}`
    voiceStatus.value = '云端语音提醒失败，已使用浏览器语音播报'
    speakWithBrowser(fallback)
  }
}

function speakWithBrowser(text) {
  if (!window.speechSynthesis || !text) return
  window.speechSynthesis.cancel()
  activeSpeech?.pause()
  const utterance = new SpeechSynthesisUtterance(text)
  utterance.lang = 'zh-CN'
  utterance.rate = 1
  window.speechSynthesis.speak(utterance)
}

async function speakOperation(text) {
  if (!text) return
  try {
    const { data } = await createSpeech(text)
    const audio = new Audio(`data:${data.audio_mime};base64,${data.audio_base64}`)
    activeSpeech?.pause()
    activeSpeech = audio
    await audio.play()
  } catch {
    speakWithBrowser(text)
  }
}

function showReminder(event) {
  markReminded(event)
  const body = `${formatClock(event.start_time)} ${event.title}`
  voiceStatus.value = `日程提醒：${body}`

  ElNotification({
    title: '日程提醒',
    message: body,
    type: 'warning',
    duration: 0,
  })

  if (notificationPermission.value === 'granted') {
    new Notification('VoiceCalendar 日程提醒', {
      body,
      tag: `voice-calendar-${event.id}`,
    })
  }

  playReminderSpeech(event)
}

function clearReminderTimers() {
  reminderTimers.forEach((timer) => clearTimeout(timer))
  reminderTimers = new Map()
}

function scheduleReminders() {
  clearReminderTimers()
  const now = Date.now()
  const remindedKeys = getRemindedKeys()

  events.value.forEach((event) => {
    if (remindedKeys.has(getReminderKey(event))) return
    const reminderAt = getReminderAt(event)
    const startAt = parseLocalDateTime(event.start_time)
    const endAt = parseLocalDateTime(event.end_time)
    if (!reminderAt || !startAt || (endAt && endAt.getTime() <= now)) return

    const delay = reminderAt.getTime() - now
    if (delay <= 0) {
      reminderTimers.set(getReminderKey(event), window.setTimeout(() => showReminder(event), IMMEDIATE_REMINDER_DELAY_MS))
      return
    }

    reminderTimers.set(getReminderKey(event), window.setTimeout(() => showReminder(event), delay))
  })
}

async function enableNotifications() {
  if (!('Notification' in window)) {
    notificationPermission.value = 'unsupported'
    ElMessage.warning('当前浏览器不支持系统通知')
    return
  }

  const permission = await Notification.requestPermission()
  notificationPermission.value = permission
  if (permission === 'granted') {
    ElMessage.success('提醒通知已开启')
    scheduleReminders()
  } else {
    ElMessage.warning('未开启系统通知，到点仍会显示页面内提醒')
  }
}

async function loadEvents() {
  listLoading.value = true
  try {
    const { data } = await getEvents()
    events.value = data
    scheduleReminders()
  } catch (error) {
    errorMessage.value = error.response?.data?.detail || '获取日程失败'
  } finally {
    listLoading.value = false
  }
}

async function executeCommand(text, source = 'manual') {
  const command = text.trim()
  if (!command) {
    ElMessage.warning('请输入日程指令')
    return
  }
  loading.value = true
  errorMessage.value = ''
  parsed.value = null
  commandResults.value = []
  hasQueryResult.value = false
  lastCommandText.value = command
  lastExecutionMessage.value = '正在解析并执行'
  lastMatchedEvents.value = []
  try {
    const { data } = await executeCalendarCommand(command)
    parsed.value = data.parsed
    commandResults.value = data.events || []
    hasQueryResult.value = data.parsed?.intent === 'query'
    lastExecutionMessage.value = data.message
    lastMatchedEvents.value = data.events?.length ? data.events : data.event ? [data.event] : []
    if (data.success) {
      ElMessage.success(data.message)
      const speechText = buildOperationSpeech(data)
      speakOperation(speechText)
      if (source === 'voice') {
        voiceStatus.value = `已执行语音指令：${data.message}`
      }
      if (data.parsed?.intent !== 'query') {
        await loadEvents()
      }
    } else {
      errorMessage.value = data.message
      lastMatchedEvents.value = []
      ElMessage.warning(data.message)
      speakOperation(data.message)
    }
  } catch (error) {
    errorMessage.value = error.response?.data?.detail || '执行指令失败'
    lastExecutionMessage.value = errorMessage.value
    lastMatchedEvents.value = []
    ElMessage.error(errorMessage.value)
    speakOperation(errorMessage.value)
  } finally {
    loading.value = false
  }
}

function buildOperationSpeech(data) {
  const intent = data.parsed?.intent
  if (intent === 'create' && data.event) {
    return `已创建日程，${data.event.title}，时间是${formatTime(data.event.start_time)}。`
  }
  if (intent === 'query') {
    return data.events?.length
      ? `已找到${data.events.length}条日程。`
      : '没有找到符合条件的日程。'
  }
  if (intent === 'delete') {
    return data.message
  }
  return data.message
}

async function runCommand() {
  await executeCommand(commandText.value)
}

async function handleUpload(uploadFile) {
  asrLoading.value = true
  errorMessage.value = ''
  try {
    const { data } = await uploadAudio(uploadFile.raw)
    recognizedText.value = data.text
    commandText.value = data.text
    ElMessage.success(data.mock ? 'mock 语音识别完成，正在执行' : '语音识别完成，正在执行')
    await executeCommand(data.text, 'voice')
  } catch (error) {
    errorMessage.value = error.response?.data?.detail || '语音识别失败'
    ElMessage.error(errorMessage.value)
  } finally {
    asrLoading.value = false
  }
}

async function startRecording() {
  if (!navigator.mediaDevices?.getUserMedia) {
    errorMessage.value = '当前浏览器不支持麦克风录音'
    ElMessage.error(errorMessage.value)
    return
  }
  errorMessage.value = ''
  voiceStatus.value = ''
  try {
    // 直接采集 PCM 数据并编码成 WAV，兼容云端一句话识别接口支持的格式。
    micStream = await navigator.mediaDevices.getUserMedia({ audio: true })
    audioContext = new (window.AudioContext || window.webkitAudioContext)()
    recordingSampleRate = audioContext.sampleRate
    recordingBuffers = []
    audioSource = audioContext.createMediaStreamSource(micStream)
    audioProcessor = audioContext.createScriptProcessor(4096, 1, 1)
    audioProcessor.onaudioprocess = (event) => {
      if (!recording.value) return
      const input = event.inputBuffer.getChannelData(0)
      recordingBuffers.push(new Float32Array(input))
    }
    audioSource.connect(audioProcessor)
    audioProcessor.connect(audioContext.destination)
    recording.value = true
    voiceStatus.value = '正在录音，请说话'
    ElMessage.success('开始语音输入')
  } catch (error) {
    errorMessage.value = '无法访问麦克风，请检查浏览器权限'
    ElMessage.error(errorMessage.value)
  }
}

async function stopRecording() {
  if (!recording.value) return
  recording.value = false
  audioProcessor?.disconnect()
  audioSource?.disconnect()
  micStream?.getTracks().forEach((track) => track.stop())
  await audioContext?.close()

  const wavBlob = encodeWav(recordingBuffers, recordingSampleRate)
  const audioFile = new File([wavBlob], `voice-calendar-${Date.now()}.wav`, {
    type: 'audio/wav'
  })
  voiceStatus.value = `已上传 ${Math.round(audioFile.size / 1024)} KB 录音，正在识别`
  await recognizeFile(audioFile)
  resetAudioState()
}

function resetAudioState() {
  audioContext = null
  audioSource = null
  audioProcessor = null
  micStream = null
  recordingBuffers = []
}

async function recognizeFile(file) {
  asrLoading.value = true
  errorMessage.value = ''
  try {
    const { data } = await uploadAudio(file)
    recognizedText.value = data.text
    commandText.value = data.text
    voiceStatus.value = data.mock ? 'mock 语音识别完成，正在执行' : '腾讯云语音识别完成，正在执行'
    ElMessage.success(data.mock ? 'mock 语音识别完成，正在执行' : '语音识别完成，正在执行')
    await executeCommand(data.text, 'voice')
  } catch (error) {
    errorMessage.value = error.response?.data?.detail || '语音识别失败'
    voiceStatus.value = errorMessage.value
    ElMessage.error(errorMessage.value)
  } finally {
    asrLoading.value = false
  }
}

function mergeBuffers(buffers) {
  const length = buffers.reduce((sum, buffer) => sum + buffer.length, 0)
  const result = new Float32Array(length)
  let offset = 0
  buffers.forEach((buffer) => {
    result.set(buffer, offset)
    offset += buffer.length
  })
  return result
}

function writeString(view, offset, value) {
  for (let i = 0; i < value.length; i += 1) {
    view.setUint8(offset + i, value.charCodeAt(i))
  }
}

function resampleAudio(samples, sourceSampleRate, targetSampleRate) {
  if (sourceSampleRate === targetSampleRate) return samples

  const ratio = sourceSampleRate / targetSampleRate
  const resultLength = Math.max(1, Math.round(samples.length / ratio))
  const result = new Float32Array(resultLength)

  for (let i = 0; i < resultLength; i += 1) {
    const sourceIndex = i * ratio
    const left = Math.floor(sourceIndex)
    const right = Math.min(left + 1, samples.length - 1)
    const weight = sourceIndex - left
    result[i] = samples[left] * (1 - weight) + samples[right] * weight
  }

  return result
}

function encodeWav(buffers, sampleRate) {
  // 腾讯云 16k_zh 按 16k WAV 上传，避免浏览器默认 48k 导致空结果。
  const rawSamples = mergeBuffers(buffers)
  const samples = resampleAudio(rawSamples, sampleRate, TENCENT_ASR_SAMPLE_RATE)
  const bytesPerSample = 2
  const buffer = new ArrayBuffer(44 + samples.length * bytesPerSample)
  const view = new DataView(buffer)

  writeString(view, 0, 'RIFF')
  view.setUint32(4, 36 + samples.length * bytesPerSample, true)
  writeString(view, 8, 'WAVE')
  writeString(view, 12, 'fmt ')
  view.setUint32(16, 16, true)
  view.setUint16(20, 1, true)
  view.setUint16(22, 1, true)
  view.setUint32(24, TENCENT_ASR_SAMPLE_RATE, true)
  view.setUint32(28, TENCENT_ASR_SAMPLE_RATE * bytesPerSample, true)
  view.setUint16(32, bytesPerSample, true)
  view.setUint16(34, 16, true)
  writeString(view, 36, 'data')
  view.setUint32(40, samples.length * bytesPerSample, true)

  let offset = 44
  for (let i = 0; i < samples.length; i += 1) {
    const sample = Math.max(-1, Math.min(1, samples[i]))
    view.setInt16(offset, sample < 0 ? sample * 0x8000 : sample * 0x7fff, true)
    offset += 2
  }

  return new Blob([view], { type: 'audio/wav' })
}

async function removeEvent(row) {
  try {
    await deleteEvent(row.id)
    clearReminderState(row)
    ElMessage.success('日程已删除')
    speakOperation(`已删除日程，${row.title}。`)
    await loadEvents()
  } catch (error) {
    if (error.response?.status === 404) {
      clearReminderState(row)
      ElMessage.warning('日程已不存在，已刷新')
      speakOperation('日程已不存在，已刷新。')
      await loadEvents()
      return
    }
    const message = error.response?.data?.detail || '删除失败'
    ElMessage.error(message)
    speakOperation(message)
  }
}

onMounted(() => {
  notificationPermission.value = 'Notification' in window ? Notification.permission : 'unsupported'
  loadEvents()
})

onUnmounted(() => {
  clearReminderTimers()
})
</script>

<template>
  <main class="page">
    <section class="workspace">
      <header class="topbar">
        <div>
          <h1>VoiceCalendar</h1>
          <p>语音交互式智能日历工具</p>
        </div>
        <div class="topbar-actions">
          <el-button
            :icon="Bell"
            :type="notificationPermission === 'granted' ? 'success' : 'default'"
            @click="enableNotifications"
          >
            {{ notificationPermission === 'granted' ? '提醒已开启' : '开启提醒' }}
          </el-button>
          <el-button :icon="Refresh" :loading="listLoading" @click="loadEvents">刷新</el-button>
        </div>
      </header>

      <section class="command-panel">
        <el-input
          v-model="commandText"
          type="textarea"
          :rows="3"
          resize="none"
          placeholder="例如：明天下午三点提醒我开会"
        />
        <div class="actions">
          <el-button type="primary" :icon="VideoPlay" :loading="loading" @click="runCommand">
            执行指令
          </el-button>
          <el-button
            v-if="!recording"
            type="success"
            :icon="Microphone"
            :loading="asrLoading"
            @click="startRecording"
          >
            开始语音指令
          </el-button>
          <el-button v-else type="danger" :icon="VideoPause" @click="stopRecording">
            停止录音
          </el-button>
          <el-upload
            action="#"
            :auto-upload="false"
            :show-file-list="false"
            :on-change="handleUpload"
            accept="audio/*"
          >
            <el-button :loading="asrLoading">上传音频文件</el-button>
          </el-upload>
        </div>
        <p v-if="voiceStatus" class="voice-status">{{ voiceStatus }}</p>
      </section>

      <el-alert
        v-if="errorMessage"
        class="status-alert"
        type="error"
        :title="errorMessage"
        show-icon
        :closable="false"
      />

      <section class="result-grid">
        <div class="panel">
          <h2>识别文本</h2>
          <p class="recognized">{{ recognizedText || '语音输入或上传音频后显示识别文本' }}</p>
        </div>
        <div class="panel">
          <h2>解析结果</h2>
          <pre>{{ parsed ? JSON.stringify(parsed, null, 2) : '执行指令后显示 DeepSeek 解析结果' }}</pre>
        </div>
      </section>

      <section v-if="agentDecisionSteps.length" class="agent-panel">
        <div class="section-head">
          <h2>AI 决策过程</h2>
          <span>DeepSeek + 本地日程上下文</span>
        </div>
        <div class="agent-steps">
          <div v-for="step in agentDecisionSteps" :key="step.label" class="agent-step">
            <span>{{ step.label }}</span>
            <strong>{{ step.value }}</strong>
          </div>
        </div>
      </section>

      <section v-if="hasQueryResult" class="query-panel">
        <div class="section-head">
          <h2>查看结果</h2>
          <span>{{ commandResults.length }} 条</span>
        </div>
        <div class="query-list">
          <div v-for="event in commandResults" :key="event.id" class="query-item">
            <strong>{{ event.title }}</strong>
            <span>{{ formatTime(event.start_time) }}</span>
            <small>提前 {{ event.reminder_minutes }} 分钟提醒</small>
          </div>
          <p v-if="!commandResults.length" class="empty-query">没有找到日程</p>
        </div>
      </section>

      <section class="calendar-panel">
        <div class="section-head">
          <h2>日历</h2>
          <div class="calendar-toolbar">
            <el-button :icon="ArrowLeft" circle @click="changeMonth(-1)" />
            <strong>{{ calendarTitle }}</strong>
            <el-button :icon="ArrowRight" circle @click="changeMonth(1)" />
            <el-button @click="backToToday">今天</el-button>
          </div>
        </div>
        <div class="month-calendar">
          <div class="weekday">周日</div>
          <div class="weekday">周一</div>
          <div class="weekday">周二</div>
          <div class="weekday">周三</div>
          <div class="weekday">周四</div>
          <div class="weekday">周五</div>
          <div class="weekday">周六</div>
          <div
            v-for="day in monthCells"
            :key="day.key"
            class="month-day"
            :class="{ muted: !day.currentMonth, today: day.today }"
          >
            <div class="month-day-head">
              <span>{{ day.day }}</span>
              <small v-if="day.events.length">{{ day.events.length }} 条</small>
            </div>
            <p class="lunar-text" :class="{ festival: day.festival }">{{ day.lunarText }}</p>
            <div class="month-day-events">
              <div v-for="event in day.events.slice(0, 3)" :key="event.id" class="calendar-event">
                <span>{{ formatClock(event.start_time) }}</span>
                <p>{{ event.title }}</p>
                <small>{{ formatClock(toLocalDateTimeString(getReminderAt(event))) }} 提醒</small>
              </div>
              <p v-if="day.events.length > 3" class="more-events">还有 {{ day.events.length - 3 }} 条</p>
            </div>
          </div>
        </div>
      </section>

      <section class="events-panel">
        <div class="section-head">
          <h2>日程列表</h2>
          <span>{{ events.length }} 条</span>
        </div>
        <el-table v-loading="listLoading" :data="events" empty-text="暂无日程" stripe>
          <el-table-column prop="title" label="标题" min-width="120" />
          <el-table-column label="开始时间" min-width="180">
            <template #default="{ row }">{{ formatTime(row.start_time) }}</template>
          </el-table-column>
          <el-table-column label="结束时间" min-width="180">
            <template #default="{ row }">{{ formatTime(row.end_time) }}</template>
          </el-table-column>
          <el-table-column label="提醒" width="100">
            <template #default="{ row }">提前 {{ row.reminder_minutes }} 分钟</template>
          </el-table-column>
          <el-table-column label="提醒时间" min-width="180">
            <template #default="{ row }">{{ formatReminder(row) }}</template>
          </el-table-column>
          <el-table-column prop="raw_text" label="原始输入" min-width="220" />
          <el-table-column label="操作" width="100" fixed="right">
            <template #default="{ row }">
              <el-button type="danger" :icon="Delete" circle plain @click="removeEvent(row)" />
            </template>
          </el-table-column>
        </el-table>
      </section>
    </section>
  </main>
</template>
