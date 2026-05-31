import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 30000
})

export function executeCalendarCommand(text) {
  return api.post('/command', { text })
}

export function getEvents() {
  return api.get('/events')
}

export function deleteEvent(id) {
  return api.delete(`/events/${id}`)
}

export function uploadAudio(file) {
  const formData = new FormData()
  formData.append('file', file)
  return api.post('/asr', formData, {
    headers: { 'Content-Type': 'multipart/form-data' }
  })
}
