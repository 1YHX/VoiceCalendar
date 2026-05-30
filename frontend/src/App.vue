<script setup>
import { computed, onMounted, ref } from 'vue'
import { Delete, Microphone, Refresh, VideoPause, VideoPlay } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
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
let audioContext = null
let audioSource = null
let audioProcessor = null
let micStream = null
let recordingBuffers = []
let recordingSampleRate = 44100
let speechRecognition = null
let browserSpeechText = ''

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

function formatMonthDay(date) {
  return `${date.getMonth() + 1}/${date.getDate()}`
}

const weekDays = computed(() => {
  const labels = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  return Array.from({ length: 7 }, (_, index) => {
    const date = new Date(today)
    date.setDate(today.getDate() + index)
    const key = date.toISOString().slice(0, 10)
    return {
      key,
      label: index === 0 ? '今天' : labels[date.getDay()],
      dateText: formatMonthDay(date),
      events: events.value.filter((event) => dateKey(event.start_time) === key)
    }
  })
})

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
  browserSpeechText = ''
  try {
    startBrowserSpeechRecognition()
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
    stopBrowserSpeechRecognition()
    errorMessage.value = '无法访问麦克风，请检查浏览器权限'
    ElMessage.error(errorMessage.value)
  }
}

async function stopRecording() {
  if (!recording.value) return
  recording.value = false
  stopBrowserSpeechRecognition()
  audioProcessor?.disconnect()
  audioSource?.disconnect()
  micStream?.getTracks().forEach((track) => track.stop())
  await audioContext?.close()

  if (browserSpeechText.trim()) {
    recognizedText.value = browserSpeechText.trim()
    commandText.value = browserSpeechText.trim()
    voiceStatus.value = '浏览器语音识别完成'
    resetAudioState()
    ElMessage.success('语音识别完成')
    return
  }

  const wavBlob = encodeWav(recordingBuffers, recordingSampleRate)
  const audioFile = new File([wavBlob], `voice-calendar-${Date.now()}.wav`, {
    type: 'audio/wav'
  })
  voiceStatus.value = `浏览器未返回文本，已上传 ${Math.round(audioFile.size / 1024)} KB 录音到七牛识别`
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

function startBrowserSpeechRecognition() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition
  if (!SpeechRecognition) {
    voiceStatus.value = '当前浏览器不支持原生语音识别，将使用七牛 ASR'
    return
  }

  speechRecognition = new SpeechRecognition()
  speechRecognition.lang = 'zh-CN'
  speechRecognition.continuous = true
  speechRecognition.interimResults = true
  speechRecognition.onresult = (event) => {
    let text = ''
    for (let i = 0; i < event.results.length; i += 1) {
      text += event.results[i][0].transcript
    }
    browserSpeechText = text.trim()
    recognizedText.value = browserSpeechText
    commandText.value = browserSpeechText
    voiceStatus.value = text ? '已识别到语音文本' : '正在听'
  }
  speechRecognition.onerror = () => {
    voiceStatus.value = '浏览器语音识别不可用，将使用七牛 ASR'
  }
  speechRecognition.start()
}

function stopBrowserSpeechRecognition() {
  if (!speechRecognition) return
  try {
    speechRecognition.stop()
  } catch (error) {
    // Ignore stop errors from already-stopped browser recognizers.
  }
  speechRecognition = null
}

async function recognizeFile(file) {
  asrLoading.value = true
  errorMessage.value = ''
  try {
    const { data } = await uploadAudio(file)
    recognizedText.value = data.text
    commandText.value = data.text
    voiceStatus.value = data.mock ? 'mock 语音识别完成' : '七牛语音识别完成'
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
          <h2>近 7 天日历</h2>
          <span>{{ events.length }} 条日程</span>
        </div>
        <div class="week-calendar">
          <div v-for="day in weekDays" :key="day.key" class="day-column">
            <div class="day-head">
              <span>{{ day.label }}</span>
              <strong>{{ day.dateText }}</strong>
            </div>
            <div class="day-events">
              <div v-for="event in day.events" :key="event.id" class="calendar-event">
                <span>{{ formatClock(event.start_time) }}</span>
                <p>{{ event.title }}</p>
              </div>
              <p v-if="day.events.length === 0" class="empty-day">暂无</p>
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
