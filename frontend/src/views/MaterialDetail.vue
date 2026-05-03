<template>
  <div class="detail-page">
    <div class="container py-4">
      <!-- Header -->
      <div class="d-flex align-items-center mb-4 gap-3">
        <RouterLink to="/materials" class="btn btn-back">← Back</RouterLink>
        <div v-if="material">
          <h1 class="h4 mb-1">{{ material.title }}</h1>
          <div class="d-flex gap-2 align-items-center">
            <span :class="statusBadge(material.status)">{{ material.status }}</span>
            <small class="text-muted">
              {{ material.source_type }} · {{ material.language }}
              <span v-if="material.duration"> · {{ fmtDuration(material.duration) }}</span>
            </small>
          </div>
        </div>
      </div>

      <!-- Toast -->
      <div class="position-fixed top-0 end-0 p-3" style="z-index:9999">
        <div v-if="toast" :class="`alert alert-${toast.type} mb-0 shadow`">{{ toast.message }}</div>
      </div>

      <!-- Processing indicator -->
      <div class="alert alert-info d-flex align-items-center gap-2" v-if="material?.status === 'processing' || material?.status === 'pending'">
        <span class="spinner-border spinner-border-sm"></span>
        Processing in background... <button class="btn btn-sm btn-outline-info ms-2" @click="loadMaterial">Refresh</button>
      </div>
      <div class="alert alert-danger" v-if="material?.status === 'failed'">
        Processing failed: {{ material.error_msg }}
      </div>

      <!-- Bulk action buttons & Sequential playback -->
      <div class="sticky-top-actions d-flex flex-wrap gap-2 mb-4" v-if="segments.length">
        <div class="btn-group btn-group-sm">
          <button class="btn btn-play-seq" v-if="!isSequencePlaying" @click="startSequence">
            ▶ Play Sequence
          </button>
          <button class="btn btn-pause-seq" v-else @click="pauseSequence">
            ⏸ Pause Sequence
          </button>
        </div>

        <button class="btn btn-bulk-anki" @click="bulkPush('anki')" :disabled="pushing" id="btn-bulk-anki">
          Push All to Anki
        </button>
        <button class="btn btn-bulk-tg" @click="bulkPush('telegram')" :disabled="pushing" id="btn-bulk-telegram">
          Push All to Telegram
        </button>
      </div>

      <!-- Segments List -->
      <div v-if="loading" class="text-center py-5">
        <div class="spinner-border text-primary"></div>
      </div>
      <div v-else-if="!segments.length && material?.status === 'done'" class="text-muted text-center py-5">
        No segments generated for this material.
      </div>

      <div class="segment-card mb-3" v-for="seg in segments" :key="seg.id" :id="`seg-card-${seg.id}`"
           :class="{ playing: currentPlayingId === seg.id }">
        <div class="card-body">
          <div class="d-flex justify-content-between align-items-center mb-2">
            <span class="badge-index">#{{ seg.index }}</span>
            <span class="badge-source ms-auto">{{ seg.audio_source_type }}</span>
          </div>

          <!-- Audio player -->
          <audio controls class="w-100 mb-3 custom-audio" 
                 :src="`/api/audio/${seg.id}`" 
                 preload="metadata"
                 :id="`audio-player-${seg.id}`"
                 @play="onAudioPlay(seg.id)"
                 @ended="onAudioEnded(seg.id)">
            Your browser does not support audio.
          </audio>

          <!-- Content section -->
          <div v-if="editingId !== seg.id">
            <p class="seg-text mb-1" @contextmenu.prevent="onContextMenu($event, seg)" @touchstart="onTouchStart($event, seg)" @touchend="onTouchEnd($event, seg)">{{ seg.text }}</p>
            <p class="seg-translation mb-2" v-if="seg.translation">{{ seg.translation }}</p>
            <div class="seg-analysis mb-2" v-if="segmentAnalysis[seg.id]">
              <small class="text-muted">💡 {{ segmentAnalysis[seg.id].slice(0, 120) }}{{ segmentAnalysis[seg.id].length > 120 ? '...' : '' }}</small>
            </div>
            <div class="seg-time" v-if="seg.start_time !== null">
              {{ fmtTime(seg.start_time) }} – {{ fmtTime(seg.end_time) }}
            </div>
          </div>
          
          <!-- Edit Form -->
          <div v-else class="edit-form mb-3">
            <textarea v-model="editForm.text" class="form-control mb-2" rows="2"></textarea>
            <input v-model="editForm.translation" class="form-control mb-2" placeholder="Chinese translation" />
            <div class="d-flex gap-2">
              <button class="btn btn-sm btn-success" @click="saveEdit(seg)">Save</button>
              <button class="btn btn-sm btn-secondary" @click="editingId = null">Cancel</button>
            </div>
          </div>

          <!-- Action buttons -->
          <div class="d-flex gap-2 mt-3 pt-2 border-top">
            <button class="btn btn-seg-action" @click="startEdit(seg)" :id="`btn-edit-${seg.id}`">Edit</button>
            <button class="btn btn-seg-push-anki" @click="pushSeg(seg, 'anki')" :disabled="pushing" :id="`btn-anki-${seg.id}`">
              Anki
            </button>
            <button class="btn btn-seg-push-tg" @click="pushSeg(seg, 'telegram')" :disabled="pushing" :id="`btn-telegram-${seg.id}`">
              Telegram
            </button>
            <button class="btn btn-seg-analysis-records" @click="showAnalysisRecords(seg)" :id="`btn-analysis-${seg.id}`">
              AI解析记录
            </button>
          </div>
        </div>
      </div>

      <!-- Custom Context Menu -->
      <div v-if="contextMenu.show" class="custom-context-menu" :style="{ left: contextMenu.x + 'px', top: contextMenu.y + 'px' }" @click.stop>
        <div class="context-menu-item" @click="doAnalyze" :class="{ disabled: analyzing }">
          <span v-if="analyzing" class="spinner-border spinner-border-sm me-2"></span>
          🔍 解析
        </div>
        <div class="context-menu-item" @click="doCopy">
          📋 复制
        </div>
      </div>

      <!-- Analysis Result Modal -->
      <div class="modal fade" ref="analysisModal" tabindex="-1">
        <div class="modal-dialog">
          <div class="modal-content">
            <div class="modal-header">
              <h5 class="modal-title">AI 解析结果</h5>
              <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
            </div>
            <div class="modal-body">
              <div v-if="analyzing" class="text-center py-4">
                <div class="spinner-border text-primary mb-2"></div>
                <p class="text-muted">AI 正在分析...</p>
              </div>
              <div v-else-if="analysisResult">
                <p class="text-muted mb-2"><strong>选中短语:</strong> {{ analysisResult.phrase }}</p>
                <div class="analysis-content" v-html="analysisResult.html"></div>
              </div>
            </div>
            <div class="modal-footer">
              <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">关闭</button>
            </div>
          </div>
        </div>
      </div>

      <!-- Analysis Records Modal -->
      <div class="modal fade" ref="recordsModal" tabindex="-1">
        <div class="modal-dialog modal-lg">
          <div class="modal-content">
            <div class="modal-header">
              <h5 class="modal-title">AI 解析记录 - 片段 #{{ recordsSegIndex }}</h5>
              <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
            </div>
            <div class="modal-body">
              <div v-if="loadingRecords" class="text-center py-3">
                <div class="spinner-border text-primary"></div>
              </div>
              <div v-else-if="!analysisRecords.length" class="text-muted text-center py-3">
                暂无解析记录
              </div>
              <div v-for="rec in analysisRecords" :key="rec.id" class="card mb-3">
                <div class="card-body">
                  <p class="mb-1"><strong>选中短语:</strong> <span class="text-primary">{{ rec.selected_phrase }}</span></p>
                  <div class="analysis-content" v-html="formatAnalysis(rec.analysis)"></div>
                  <small class="text-muted">{{ new Date(rec.created_at).toLocaleString() }}</small>
                </div>
              </div>
            </div>
            <div class="modal-footer">
              <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">关闭</button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { useRoute } from 'vue-router'
import api, { materialsApi, segmentsApi, usersApi, analysisApi } from '../api/index.js'
import { Modal } from 'bootstrap'

const route = useRoute()
const materialId = Number(route.params.id)

const material = ref(null)
const segments = ref([])
const loading = ref(false)
const pushing = ref(false)
const toast = ref(null)
const editingId = ref(null)
const editForm = ref({ text: '', translation: '' })
const userConfig = ref(null)

// Context menu state
const contextMenu = ref({ show: false, x: 0, y: 0, segId: null, selectedPhrase: '' })
let longPressTimer = null
let touchStartX = 0
let touchStartY = 0

// AI Analysis state
const analyzing = ref(false)
const analysisResult = ref(null)
const analysisModal = ref(null)
let analysisModalInstance = null

// Analysis records state
const segmentAnalysis = ref({})  // segId -> latest analysis preview
const analysisRecords = ref([])
const loadingRecords = ref(false)
const recordsSegIndex = ref(0)
const recordsModal = ref(null)
let recordsModalInstance = null

// -- Context Menu --
function onContextMenu(event, seg) {
  const selection = window.getSelection()
  const selectedText = selection ? selection.toString().trim() : ''

  if (!selectedText) return

  contextMenu.value = {
    show: true,
    x: event.clientX,
    y: event.clientY,
    segId: seg.id,
    selectedPhrase: selectedText,
  }
}

function onTouchStart(event, seg) {
  const selection = window.getSelection()
  const selectedText = selection ? selection.toString().trim() : ''

  touchStartX = event.touches[0].clientX
  touchStartY = event.touches[0].clientY

  longPressTimer = setTimeout(() => {
    if (selectedText) {
      contextMenu.value = {
        show: true,
        x: touchStartX,
        y: touchStartY,
        segId: seg.id,
        selectedPhrase: selectedText,
      }
    }
  }, 600)
}

function onTouchEnd() {
  clearTimeout(longPressTimer)
}

function closeContextMenu() {
  contextMenu.value.show = false
}

function doCopy() {
  navigator.clipboard.writeText(contextMenu.value.selectedPhrase).then(() => {
    showToast('已复制', 'success')
  }).catch(() => {
    showToast('复制失败', 'danger')
  })
  closeContextMenu()
}

// -- AI Analysis --
function getSurroundingContext(segId) {
  const idx = segments.value.findIndex(s => s.id === segId)
  if (idx === -1) return []

  const start = Math.max(0, idx - 1)
  const end = Math.min(segments.value.length, idx + 1)

  return segments.value.slice(start, end).map(s => ({
    index: s.index,
    text: s.text,
  }))
}

async function doAnalyze() {
  const segId = contextMenu.value.segId
  const phrase = contextMenu.value.selectedPhrase

  closeContextMenu()

  if (!userConfig.value?.ai_base_url || !userConfig.value?.ai_api_key) {
    showToast('请先在设置页面配置 AI Base URL 和 API Key', 'warning')
    return
  }

  analyzing.value = true
  analysisResult.value = null

  // Show modal
  if (!analysisModalInstance && analysisModal.value) {
    analysisModalInstance = new Modal(analysisModal.value)
  }
  analysisModalInstance?.show()

  try {
    const context = getSurroundingContext(segId)
    const contextStr = context.map(c => `[#${c.index}] ${c.text}`).join('\n')

    // Get immediate word context (5 words before/after) within the segment
    const seg = segments.value.find(s => s.id === segId)
    const segText = seg?.text || ''
    const phraseIdx = segText.indexOf(phrase)
    let immediateContext = phrase
    if (phraseIdx !== -1) {
      const before = segText.slice(0, phraseIdx).trim()
      const after = segText.slice(phraseIdx + phrase.length).trim()
      const beforeWords = before.split(/\s+/).slice(-5).join(' ')
      const afterWords = after.split(/\s+/).slice(0, 5).join(' ')
      immediateContext = `${beforeWords} **${phrase}** ${afterWords}`.trim()
    }

    const prompt = `You are an English language tutor. Analyze the phrase "${phrase}" from this sentence: "${immediateContext}"

Full transcript context:
${contextStr}

Please provide a concise analysis in Chinese:

1. 风格要求：

极简： 能用 5 个字说明白，绝不用 10 个字。

大白话： 像跟 5 岁小朋友说话一样，直白、简单。

拒绝脑补： 不要分析心路历程，只说最直观的意思。

2. 结构要求：

短语整体含义：一句话说明在文中的意思。

逐词解析：

介词/副词/表语：给出在文中的意境，这里要用英文解释

高级/核心词：用最简单的同义词替换，这里要用英文解释

例句：1-2 个极简的常用句子。

3. 负面约束（禁止出现）：

禁止说“前者...后者...”。

禁止说“隐喻”、“由下而上”、“发展轨迹”、“社会性成熟”等虚词。

禁止进行深度语义对比。

Keep it concise. Use plain text, no markdown other than **bold** for headers.`

    const baseUrl = userConfig.value.ai_base_url.replace(/\/+$/, '')
    const response = await fetch(`${baseUrl}/chat/completions`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${userConfig.value.ai_api_key}`,
      },
      body: JSON.stringify({
        model: userConfig.value.ai_model || 'gpt-3.5-turbo',
        messages: [{ role: 'user', content: prompt }],
        temperature: 0.7,
        max_tokens: 800,
      }),
    })

    if (!response.ok) {
      const errData = await response.json().catch(() => ({}))
      throw new Error(errData.error?.message || `API error: ${response.status}`)
    }

    const data = await response.json()
    const analysis = data.choices?.[0]?.message?.content || 'No analysis returned'

    analysisResult.value = {
      phrase,
      html: formatAnalysis(analysis),
    }

    // Save to backend
    await analysisApi.save(segId, {
      selected_phrase: phrase,
      analysis,
    })

    // Update preview
    segmentAnalysis.value[segId] = analysis

    showToast('解析完成', 'success')
  } catch (e) {
    showToast(`解析失败: ${e.message}`, 'danger')
  } finally {
    analyzing.value = false
  }
}

function formatAnalysis(text) {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\n/g, '<br>')
}

// -- Analysis Records --
async function showAnalysisRecords(seg) {
  const segId = seg.id
  recordsSegIndex.value = seg.index
  loadingRecords.value = true
  analysisRecords.value = []

  if (!recordsModalInstance && recordsModal.value) {
    recordsModalInstance = new Modal(recordsModal.value)
  }
  recordsModalInstance?.show()

  try {
    const res = await analysisApi.forSegment(segId)
    analysisRecords.value = res.data
  } catch (e) {
    showToast('加载解析记录失败', 'danger')
  } finally {
    loadingRecords.value = false
  }
}

async function loadAllAnalysisPreviews() {
  // Load latest analysis for each segment to show preview
  if (!segments.value.length) return
  try {
    const res = await analysisApi.list(1, 200)
    const records = res.data || []
    const previews = {}
    for (const r of records) {
      if (!previews[r.segment_id]) {
        previews[r.segment_id] = r.analysis
      }
    }
    segmentAnalysis.value = previews
  } catch {}
}

// Audio sequence logic
const isSequencePlaying = ref(false)
const currentPlayingId = ref(null)
let isProgrammaticPlay = false

function onAudioPlay(segId) {
  if (!isProgrammaticPlay) {
    // User manually clicked play (Single Play), turn off sequence mode
    isSequencePlaying.value = false
  }
  isProgrammaticPlay = false // reset
  
  // Pause other players
  if (currentPlayingId.value && currentPlayingId.value !== segId) {
    const prev = document.getElementById(`audio-player-${currentPlayingId.value}`)
    if (prev) prev.pause()
  }
  currentPlayingId.value = segId
}

function onAudioEnded(segId) {
  if (isSequencePlaying.value) {
    const idx = segments.value.findIndex(s => s.id === segId)
    if (idx !== -1 && idx < segments.value.length - 1) {
      const nextSeg = segments.value[idx + 1]
      const nextAudio = document.getElementById(`audio-player-${nextSeg.id}`)
      if (nextAudio) {
        // Scroll to next segment
        nextAudio.scrollIntoView({ behavior: 'smooth', block: 'center' })
        isProgrammaticPlay = true
        nextAudio.play()
      }
    } else {
      isSequencePlaying.value = false
    }
  }
}

function startSequence() {
  isSequencePlaying.value = true
  // Start from first segment OR current playing
  let segToPlay = segments.value[0]
  if (currentPlayingId.value) {
    const currIdx = segments.value.findIndex(s => s.id === currentPlayingId.value)
    if (currIdx !== -1) segToPlay = segments.value[currIdx]
  }

  if (segToPlay) {
    const audio = document.getElementById(`audio-player-${segToPlay.id}`)
    if (audio) {
      audio.scrollIntoView({ behavior: 'smooth', block: 'center' })
      isProgrammaticPlay = true
      audio.play()
    }
  }
}

function pauseSequence() {
  isSequencePlaying.value = false
  if (currentPlayingId.value) {
    const audio = document.getElementById(`audio-player-${currentPlayingId.value}`)
    if (audio) audio.pause()
  }
}

async function loadMaterial() {
  const res = await materialsApi.get(materialId)
  material.value = res.data
}

async function loadSegments() {
  loading.value = true
  try {
    const res = await materialsApi.getSegments(materialId)
    segments.value = res.data
  } finally {
    loading.value = false
  }
}

// --- AnkiConnect Frontend Helpers ---
async function ankiRequest(action, params = {}) {
  const url = userConfig.value?.anki_connect_url || 'http://127.0.0.1:8765'
  try {
    const body = JSON.stringify({ action, version: 6, params })
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: body
    })
    if (!res.ok) throw new Error(`AnkiConnect HTTP error! status: ${res.status}`)
    const data = await res.json()
    if (data.error) throw new Error(data.error)
    return data.result
  } catch (e) {
    if (e.name === 'TypeError' && (e.message === 'Failed to fetch' || e.message.includes('NetworkError'))) {
      throw new Error(`Connection failed to ${url}. \n1. Is Anki/Ankiconnect running?\n2. If using Android, check IP and set "CORS Host" to "*" in App settings.`)
    }
    throw e
  }
}

function blobToBase64(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onloadend = () => {
      const b64 = reader.result.split(',')[1]
      resolve(b64)
    }
    reader.onerror = reject
    reader.readAsDataURL(blob)
  })
}

async function doAnkiPush(seg) {
  const shareUrl = `${window.location.origin}/share/${materialId}#seg-${seg.id}`
  const audioFilename = `seg_${seg.id}_${Date.now()}.mp3`

  // 1. Download audio from backend API
  const audioRes = await api.get(`/audio/${seg.id}`, { responseType: 'blob' })
  const b64Data = await blobToBase64(audioRes.data)

  // 2. Ensure deck exists (Optional for Android API as it doesn't support createDeck)
  const deckName = userConfig.value?.anki_deck_name || "English::Listening"
  try {
    await ankiRequest('createDeck', { deck: deckName })
  } catch (e) {
    console.warn("createDeck failed or unsupported, continuing...", e.message)
  }

  // 3. Store media - Android API returns the FINAL filename (it renames to avoid collisions)
  const finalFilename = await ankiRequest('storeMediaFile', {
    filename: audioFilename,
    data: b64Data
  }) || audioFilename

  // 4. Add Note
  let front = seg.text
  if (seg.translation) front += `<br><small style='color:#666'>${seg.translation}</small>`

  // Append analysis records if any
  const analysisPreview = segmentAnalysis.value[seg.id]
  if (analysisPreview) {
    const cleanAnalysis = analysisPreview
      .replace(/\*\*/g, '')
      .replace(/\n/g, '<br>')
    front += `<br><br><small style='color:#6f42c1'><strong>💡 AI解析:</strong><br>${cleanAnalysis}</small>`
  }

  front += `<br><small><a href='${shareUrl}' style='color:#4a9eff'>🔗 View online</a></small>`

  // Use the filename returned by the server
  let back = `[sound:${finalFilename}]`

  const noteId = await ankiRequest('addNote', {
    note: {
      deckName: deckName,
      modelName: userConfig.value?.anki_model_name || "Basic",
      fields: { "正面": front, "背面": back },
      options: { allowDuplicate: false }
    }
  })
  
  if (!noteId) throw new Error('AnkiConnect returned null (duplicate or error)')
  return noteId
}

async function pushSeg(seg, platform) {
  pushing.value = true
  try {
    if (platform === 'anki') {
      try {
        const noteId = await doAnkiPush(seg)
        await segmentsApi.push(seg.id, 'anki', noteId)
        showToast(`Sent to Anki!`, 'success')
      } catch (e) {
        let msg = e.message
        if (msg.includes('CORS')) {
          msg = 'Anki blocked the request. Please add this site to webCorsOriginList in AnkiConnect settings.'
        }
        showToast(`Anki error: ${msg}`, 'danger')
      }
    } else {
      await segmentsApi.push(seg.id, platform)
      showToast(`Sent to ${platform}!`, 'success')
    }
  } catch (e) {
    const detail = e.response?.data?.detail || e.message || `Push to ${platform} failed`
    showToast(detail, 'danger')
  } finally {
    pushing.value = false
  }
}

async function bulkPush(platform) {
  if (!confirm(`Push all ${segments.value.length} segments to ${platform}?`)) return
  pushing.value = true
  let successCount = 0
  let failCount = 0
  let lastError = null

  try {
    if (platform === 'anki') {
      for (const seg of segments.value) {
        try {
          const noteId = await doAnkiPush(seg)
          await segmentsApi.push(seg.id, 'anki', noteId)
          successCount++
        } catch (e) {
          failCount++
          lastError = e.message
          console.error("Failed seg:", seg.id, e)
          if (e.message.includes('Connection refused') || e.message.includes('CORS')) {
            throw e // Stop early if it's a connectivity/config issue
          }
        }
      }
      
      if (successCount === segments.value.length) {
        showToast(`Successfully pushed all ${successCount} segments to Anki!`, 'success')
      } else if (successCount > 0) {
        showToast(`Pushed ${successCount} segments, but ${failCount} failed.`, 'warning')
      } else {
        showToast(`Bulk push failed: ${lastError || 'All segments failed'}`, 'danger')
      }
    } else {
      const res = await materialsApi.push(materialId, platform)
      const results = res.data // Array of PushRecord
      successCount = results.filter(r => r.status === 'sent').length
      failCount = results.filter(r => r.status === 'failed').length
      
      if (failCount === 0) {
        showToast(`All segments pushed to ${platform}!`, 'success')
      } else if (successCount > 0) {
        showToast(`Pushed ${successCount} segments, but ${failCount} failed.`, 'warning')
      } else {
        const errorMsg = results.find(r => r.status === 'failed')?.error_msg || 'Unknown error'
        showToast(`Bulk push failed: ${errorMsg}`, 'danger')
      }
    }
  } catch (e) {
    showToast(e.response?.data?.detail || e.message || 'Bulk push failed', 'danger')
  } finally {
    pushing.value = false
  }
}

function startEdit(seg) {
  editingId.value = seg.id
  editForm.value = { text: seg.text, translation: seg.translation || '' }
}

async function saveEdit(seg) {
  try {
    const res = await segmentsApi.update(seg.id, editForm.value)
    const idx = segments.value.findIndex(s => s.id === seg.id)
    if (idx !== -1) segments.value[idx] = res.data
    editingId.value = null
    showToast('Saved', 'success')
  } catch {
    showToast('Save failed', 'danger')
  }
}

function statusBadge(status) {
  const map = {
    pending: 'badge bg-secondary', processing: 'badge bg-warning text-dark',
    done: 'badge bg-success', failed: 'badge bg-danger',
  }
  return map[status] || 'badge bg-light text-dark'
}

function fmtDuration(s) {
  const m = Math.floor(s / 60), sec = Math.floor(s % 60)
  return `${m}:${String(sec).padStart(2, '0')}`
}

function fmtTime(s) {
  if (s == null) return ''
  const m = Math.floor(s / 60), sec = (s % 60).toFixed(1)
  return `${m}:${String(Math.floor(s % 60)).padStart(2, '0')}.${sec.split('.')[1]}`
}

function showToast(msg, type = 'info') {
  toast.value = { message: msg, type }
  setTimeout(() => { toast.value = null }, 4000)
}

onMounted(async () => {
  try {
    const uRes = await usersApi.me()
    userConfig.value = uRes.data
  } catch(e) {}
  await loadMaterial()
  await loadSegments()
  loadAllAnalysisPreviews()

  document.addEventListener('click', closeContextMenu)
})

onBeforeUnmount(() => {
  document.removeEventListener('click', closeContextMenu)
  clearTimeout(longPressTimer)
})
</script>

<style scoped>
.detail-page {
  min-height: 100vh;
  background: #f8f9fa;
  color: #212529;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  overflow-y: auto; /* Ensure vertical scrolling is enabled */
}

.btn-back {
  background: white;
  border: 1px solid #dee2e6;
  color: #6c757d;
  font-weight: 500;
  transition: all 0.2s;
}
.btn-back:hover {
  background: #e9ecef;
  color: #343a40;
}

.sticky-top-actions {
  position: sticky;
  top: 72px; /* Navbar height + small gap */
  z-index: 1000;
  background: rgba(248, 249, 250, 0.9);
  backdrop-filter: blur(8px);
  padding: 10px 0;
  border-bottom: 1px solid rgba(0,0,0,0.05);
}

.segment-card {
  background: white;
  border: 1px solid #e9ecef;
  border-radius: 12px;
  box-shadow: 0 2px 4px rgba(0,0,0,0.02);
  transition: transform 0.2s, box-shadow 0.2s, border-color 0.2s;
}

.segment-card:hover {
  box-shadow: 0 4px 12px rgba(0,0,0,0.05);
}

.segment-card.playing {
  border-left: 4px solid #007bff;
  background: #f0f7ff;
}

.badge-index {
  font-size: 0.75rem;
  font-weight: 700;
  color: #6c757d;
  background: #e9ecef;
  padding: 2px 8px;
  border-radius: 4px;
}

.badge-source {
  font-size: 0.7rem;
  color: #adb5bd;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.seg-text {
  font-size: 1.05rem;
  line-height: 1.6;
  color: #212529;
}

.seg-translation {
  font-size: 0.95rem;
  color: #6c757d;
  font-style: italic;
}

.seg-time {
  font-size: 0.75rem;
  color: #adb5bd;
}

.custom-audio {
  height: 40px;
  border-radius: 8px;
}

/* Action buttons */
.btn-play-seq { background: #007bff; color: white; border: none; }
.btn-play-seq:hover { background: #0056b3; }

.btn-pause-seq { background: #ffc107; color: #212529; border: none; }
.btn-pause-seq:hover { background: #e0a800; }

.btn-bulk-anki { background: #6f42c1; color: white; border: none; font-size: 0.85rem; padding: 4px 12px; border-radius: 6px; }
.btn-bulk-tg { background: #17a2b8; color: white; border: none; font-size: 0.85rem; padding: 4px 12px; border-radius: 6px; }

.btn-seg-action { font-size: 0.8rem; padding: 2px 10px; border: 1px solid #dee2e6; background: white; color: #495057; border-radius: 4px; }
.btn-seg-action:hover { background: #f8f9fa; }

.btn-seg-push-anki { font-size: 0.8rem; padding: 2px 10px; border: 1px solid #6f42c1; background: transparent; color: #6f42c1; border-radius: 4px; }
.btn-seg-push-anki:hover { background: #6f42c1; color: white; }

.btn-seg-push-tg { font-size: 0.8rem; padding: 2px 10px; border: 1px solid #17a2b8; background: transparent; color: #17a2b8; border-radius: 4px; }
.btn-seg-push-tg:hover { background: #17a2b8; color: white; }

.edit-form .form-control {
  font-size: 0.9rem;
  border-radius: 8px;
}

/* Context Menu */
.custom-context-menu {
  position: fixed;
  z-index: 10500;
  background: white;
  border: 1px solid #dee2e6;
  border-radius: 8px;
  box-shadow: 0 4px 16px rgba(0,0,0,0.12);
  min-width: 200px;
  padding: 4px 0;
}

.context-menu-item {
  padding: 8px 16px;
  cursor: pointer;
  font-size: 0.9rem;
  color: #212529;
  transition: background 0.15s;
  white-space: nowrap;
}

.context-menu-item:hover {
  background: #f0f7ff;
  color: #0d6efd;
}

.context-menu-item.disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* Analysis content */
.analysis-content {
  font-size: 0.9rem;
  line-height: 1.7;
  color: #343a40;
  white-space: pre-line;
}

/* Analysis preview in segment */
.seg-analysis {
  font-size: 0.85rem;
  color: #6f42c1;
  border-left: 2px solid #6f42c1;
  padding-left: 8px;
}

/* Analysis records button */
.btn-seg-analysis-records {
  font-size: 0.8rem;
  padding: 2px 10px;
  border: 1px solid #6f42c1;
  background: transparent;
  color: #6f42c1;
  border-radius: 4px;
}
.btn-seg-analysis-records:hover {
  background: #6f42c1;
  color: white;
}
</style>
