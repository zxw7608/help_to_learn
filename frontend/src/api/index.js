import axios from 'axios'
import { useAuthStore } from '../stores/auth.js'

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
})

// Attach access token to every request
api.interceptors.request.use((config) => {
  const auth = useAuthStore()
  if (auth.accessToken) {
    config.headers.Authorization = `Bearer ${auth.accessToken}`
  }
  return config
})

// On 401, try to refresh; on failure, redirect to login
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const auth = useAuthStore()
    if (error.response?.status === 401 && auth.refreshToken) {
      try {
        const res = await axios.post('/api/auth/refresh', {
          refresh_token: auth.refreshToken,
        })
        auth.setTokens(res.data.access_token, auth.refreshToken)
        error.config.headers.Authorization = `Bearer ${res.data.access_token}`
        return axios(error.config)
      } catch {
        auth.logout()
        window.location.href = '/login'
      }
    }
    return Promise.reject(error)
  }
)

// ── Auth ─────────────────────────────────────────
export const authApi = {
  register: (data) => api.post('/auth/register', data),
  login: (data) => api.post('/auth/login', data),
}

// ── Materials ────────────────────────────────────
export const materialsApi = {
  list: (page = 1, size = 20, materialType = null) => {
    const params = { page, size }
    if (materialType) params.material_type = materialType
    return api.get('/materials', { params })
  },
  get: (id) => api.get(`/materials/${id}`),
  delete: (id) => api.delete(`/materials/${id}`),
  uploadFile: (formData) => api.post('/materials/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 120000,
  }),
  importUrlMedia: (data) => api.post('/materials/url-media', data),
  importUrlArticle: (data) => api.post('/materials/url-article', data),
  importText: (data) => api.post('/materials/text', data),
  importTextSnippet: (data) => api.post('/materials/text-snippet', data),
  getSegments: (id) => api.get(`/materials/${id}/segments`),
  push: (id, platform) => api.post(`/materials/${id}/push`, { platform }),
  reExecute: (id) => api.post(`/materials/${id}/re-execute`),
  deleteStorage: (id) => api.delete(`/materials/${id}/storage`),
}

// ── Segments ─────────────────────────────────────
export const segmentsApi = {
  get: (id) => api.get(`/segments/${id}`),
  update: (id, data) => api.patch(`/segments/${id}`, data),
  push: (id, platform, anki_note_id = null) => api.post(`/segments/${id}/push`, { platform, anki_note_id }),
  pushRecords: (id) => api.get(`/segments/${id}/push-records`),
}

// ── Jobs ─────────────────────────────────────────
export const jobsApi = {
  get: (id) => api.get(`/jobs/${id}`),
}

// ── Users ────────────────────────────────────────
export const usersApi = {
  me: () => api.get('/users/me'),
  update: (data) => api.patch('/users/me', data),
  uploadCookies: (formData) => api.post('/users/me/cookies', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  }),
  listInviteCodes: () => api.get('/users/me/invite-codes'),
  generateInviteCode: () => api.post('/users/me/invite-codes'),
}

// ── Admin ─────────────────────────────────────────
export const adminApi = {
  getRegistrationSettings: () => api.get('/admin/registration'),
  updateRegistrationSettings: (data) => api.patch('/admin/registration', data),
  listInviteCodes: () => api.get('/admin/invite-codes'),
  createInviteCode: (data) => api.post('/admin/invite-codes', data),
}

// ── Analysis ─────────────────────────────────────
export const analysisApi = {
  save: (segmentId, data) => api.post(`/segments/${segmentId}/analysis`, data),
  forSegment: (segmentId) => api.get(`/segments/${segmentId}/analysis`),
  list: (page = 1, size = 20) => api.get('/analysis-records', { params: { page, size } }),
}

export default api
