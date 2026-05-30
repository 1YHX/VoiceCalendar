<script setup>
import { onMounted, ref } from 'vue'
import { Delete, Microphone, Refresh, VideoPlay } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { createEventByCommand, deleteEvent, getEvents, uploadAudio } from './api/calendar'

const commandText = ref('明天下午三点提醒我开会')
const recognizedText = ref('')
const parsed = ref(null)
const events = ref([])
const loading = ref(false)
const listLoading = ref(false)
const asrLoading = ref(false)
const errorMessage = ref('')

function formatTime(value) {
  if (!value) return '-'
  return value.replace('T', ' ').slice(0, 19)
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
          <el-upload
            action="#"
            :auto-upload="false"
            :show-file-list="false"
            :on-change="handleUpload"
            accept="audio/*"
          >
            <el-button :icon="Microphone" :loading="asrLoading">上传音频</el-button>
          </el-upload>
        </div>
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
          <p class="recognized">{{ recognizedText || '上传音频后显示 mock ASR 文本' }}</p>
        </div>
        <div class="panel">
          <h2>解析结果</h2>
          <pre>{{ parsed ? JSON.stringify(parsed, null, 2) : '执行指令后显示 DeepSeek 解析结果' }}</pre>
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

