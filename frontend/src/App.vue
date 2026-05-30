<script setup>
import { computed, onMounted, ref } from 'vue'
import {
  ArrowLeft,
  ArrowRight,
  Delete,
  Microphone,
  Refresh,
  VideoPause,
  VideoPlay
} from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { Solar } from 'lunar-javascript'
import { createEventByCommand, deleteEvent, getEvents, uploadAudio } from './api/calendar'

const commandText = ref('明天下午三点提醒我开会')
const recognizedText = ref('')
const parsed = ref(null)
const events = ref([])
const loading = ref(false)
const listLoading = ref(false)
const asrLoading = ref(false)
const recording = ref(false)
const errorMessage = ref('')
const voiceStatus = ref('')
const calendarCursor = ref(new Date())
let audioContext = null
let audioSource = null
let audioProcessor = null
let micStream = null
let recordingBuffers = []
let recordingSampleRate = 44100

function formatTime(value) {
  if (!value) return '-'
  return value.replace('T', ' ').slice(0, 19)
}

function formatClock(value) {
  if (!value) return '--:--'
  return value.replace('T', ' ').slice(11, 16)
}

function dateKey(value) {
  return value.replace('T', ' ').slice(0, 10)
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

async function loadEvents() {
  listLoading.value = true
  try {
    const { data } = await getEvents()
    events.value = data
  } catch (error) {
    errorMessage.value = error.response?.data?.detail || '获取日程失败'
  } finally {
    listLoading.value = false
  }
}

async function runCommand() {
  if (!commandText.value.trim()) {
    ElMessage.warning('请输入日程指令')
    return
  }
  loading.value = true
  errorMessage.value = ''
  parsed.value = null
  try {
    const { data } = await createEventByCommand(commandText.value.trim())
    parsed.value = data.parsed
    if (data.success) {
      ElMessage.success(data.message)
      await loadEvents()
    } else {
      errorMessage.value = data.message
      ElMessage.warning(data.message)
    }
  } catch (error) {
    errorMessage.value = error.response?.data?.detail || '执行指令失败'
    ElMessage.error(errorMessage.value)
  } finally {
    loading.value = false
  }
}

async function handleUpload(uploadFile) {
  asrLoading.value = true
  errorMessage.value = ''
  try {
    const { data } = await uploadAudio(uploadFile.raw)
    recognizedText.value = data.text
    commandText.value = data.text
    ElMessage.success(data.mock ? 'mock 语音识别完成' : '语音识别完成')
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
    voiceStatus.value = data.mock ? 'mock 语音识别完成' : '腾讯云语音识别完成'
    ElMessage.success(data.mock ? 'mock 语音识别完成' : '语音识别完成')
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

function encodeWav(buffers, sampleRate) {
  // 浏览器录音得到的是 Float32 PCM，这里封装为 16-bit mono WAV 文件上传。
  const samples = mergeBuffers(buffers)
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
  view.setUint32(24, sampleRate, true)
  view.setUint32(28, sampleRate * bytesPerSample, true)
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

async function removeEvent(id) {
  try {
    await deleteEvent(id)
    ElMessage.success('日程已删除')
    await loadEvents()
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || '删除失败')
  }
}

onMounted(loadEvents)
</script>

<template>
  <main class="page">
    <section class="workspace">
      <header class="topbar">
        <div>
          <h1>VoiceCalendar</h1>
          <p>语音交互式智能日历工具 MVP</p>
        </div>
        <el-button :icon="Refresh" :loading="listLoading" @click="loadEvents">刷新</el-button>
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
            开始语音输入
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
            <template #default="{ row }">{{ row.reminder_minutes }} 分钟</template>
          </el-table-column>
          <el-table-column prop="raw_text" label="原始输入" min-width="220" />
          <el-table-column label="操作" width="100" fixed="right">
            <template #default="{ row }">
              <el-button type="danger" :icon="Delete" circle plain @click="removeEvent(row.id)" />
            </template>
          </el-table-column>
        </el-table>
      </section>
    </section>
  </main>
</template>
