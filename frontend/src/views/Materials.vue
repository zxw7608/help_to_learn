<template>
  <div class="container-fluid py-4">
    <div class="d-flex justify-content-between align-items-center mb-4">
      <h1 class="h4 mb-0">{{ isTemporary ? 'Temporary Materials' : 'Materials' }}</h1>
      <button class="btn btn-primary" data-bs-toggle="modal" data-bs-target="#addModal" id="btn-add-material">
        + Add {{ isTemporary ? 'Temporary' : 'Material' }}
      </button>
    </div>

    <!-- Toast -->
    <div class="position-fixed top-0 end-0 p-3" style="z-index:9999">
      <div v-if="toast" :class="`alert alert-${toast.type} mb-0 shadow`">{{ toast.message }}</div>
    </div>

    <!-- Materials Table -->
    <div class="card shadow-sm">
      <div class="card-body p-0">
        <div class="table-responsive">
          <table class="table table-hover mb-0">
            <thead class="table-light">
              <tr>
                <th>Title</th>
                <th>Type</th>
                <th>Category</th>
                <th>Status</th>
                <th>Language</th>
                <th>Created</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="loading"><td colspan="7" class="text-center py-4">
                <span class="spinner-border spinner-border-sm"></span> Loading...
              </td></tr>
              <tr v-else-if="!materials.length"><td colspan="7" class="text-center py-4 text-muted">
                No materials yet. Click <strong>Add Material</strong> to get started.
              </td></tr>
              <tr v-for="m in materials" :key="m.id" class="cursor-pointer" @click="goDetail(m.id)">
                <td class="fw-semibold">{{ m.title }}</td>
                <td><span class="badge bg-secondary">{{ m.source_type }}</span></td>
                <td>
                  <span :class="m.material_type === 'temporary' ? 'badge bg-info' : 'badge bg-light text-dark'">
                    {{ m.material_type }}
                  </span>
                </td>
                <td>
                  <span :class="statusBadge(m.status)">{{ m.status }}</span>
                </td>
                <td>{{ m.language }}</td>
                <td class="text-muted small">{{ fmtDate(m.created_at) }}</td>
                <td>
                  <button class="btn btn-sm btn-outline-warning me-1"
                    @click.stop="reExecute(m)"
                    title="Re-execute processing"
                    :id="`btn-reexecute-${m.id}`">🔄</button>
                  <button class="btn btn-sm btn-outline-secondary me-1"
                    @click.stop="cleanupStorage(m)"
                    title="Clean disk storage (permanent)"
                    :id="`btn-cleanup-${m.id}`">🧹</button>
                  <button class="btn btn-sm btn-outline-danger"
                    @click.stop="confirmDelete(m)"
                    :id="`btn-delete-${m.id}`">✕</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- Pagination -->
    <div class="d-flex justify-content-between align-items-center mt-3" v-if="total > pageSize">
      <small class="text-muted">Showing {{ materials.length }} of {{ total }}</small>
      <div>
        <button class="btn btn-sm btn-outline-secondary me-1" :disabled="page === 1" @click="page--; load()">‹ Prev</button>
        <button class="btn btn-sm btn-outline-secondary" :disabled="page * pageSize >= total" @click="page++; load()">Next ›</button>
      </div>
    </div>
  </div>

  <!-- Add Material Modal -->
  <div class="modal fade" id="addModal" tabindex="-1" aria-labelledby="addModalLabel" aria-hidden="true">
    <div class="modal-dialog modal-lg">
      <div class="modal-content">
        <div class="modal-header">
          <h5 class="modal-title" id="addModalLabel">Add Material</h5>
          <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
        </div>
        <div class="modal-body">
          <!-- Tabs -->
          <ul class="nav nav-tabs mb-3" id="importTabs">
            <li class="nav-item" v-for="tab in tabs" :key="tab.key">
              <button :class="['nav-link', activeTab === tab.key ? 'active' : '']"
                      @click="activeTab = tab.key">
                {{ tab.label }}
              </button>
            </li>
          </ul>

          <div class="alert alert-danger" v-if="importError">{{ importError }}</div>

          <!-- Upload File -->
          <div v-if="activeTab === 'upload'">
            <div class="mb-3">
              <label class="form-label">Title</label>
              <input v-model="forms.upload.title" type="text" class="form-control" placeholder="Leave empty to use filename" />
            </div>
            <div class="mb-3">
              <label class="form-label">File (mp4, mp3, wav, m4a, mkv)</label>
              <input type="file" class="form-control" accept=".mp4,.mp3,.wav,.m4a,.mkv,.webm,.aac"
                     @change="e => forms.upload.file = e.target.files[0]" id="file-upload-input" />
            </div>
            <div class="mb-3">
              <label class="form-label">Language</label>
              <input v-model="forms.upload.language" type="text" class="form-control" placeholder="en" />
            </div>
          </div>

          <!-- Media URL -->
          <div v-if="activeTab === 'url_media'">
            <div class="mb-3">
              <label class="form-label">YouTube / Bilibili URL</label>
              <input v-model="forms.url_media.url" type="url" class="form-control"
                     placeholder="https://www.youtube.com/watch?v=..." />
            </div>
            <div class="mb-3">
              <label class="form-label">Title (optional)</label>
              <input v-model="forms.url_media.title" type="text" class="form-control" />
            </div>
            <div class="mb-3">
              <label class="form-label">Language</label>
              <input v-model="forms.url_media.language" type="text" class="form-control" placeholder="en" />
            </div>
          </div>

          <!-- Article URL -->
          <div v-if="activeTab === 'url_article'">
            <div class="mb-3">
              <label class="form-label">Article URL</label>
              <input v-model="forms.url_article.url" type="url" class="form-control"
                     placeholder="https://example.com/article" />
            </div>
            <div class="mb-3">
              <label class="form-label">Title (optional)</label>
              <input v-model="forms.url_article.title" type="text" class="form-control" />
            </div>
            <div class="mb-3">
              <label class="form-label">Language</label>
              <input v-model="forms.url_article.language" type="text" class="form-control" placeholder="en" />
            </div>
          </div>

          <!-- Plain Text -->
          <div v-if="activeTab === 'text'">
            <div class="mb-3">
              <label class="form-label">Title</label>
              <input v-model="forms.text.title" type="text" class="form-control" required />
            </div>
            <div class="mb-3">
              <label class="form-label">Text</label>
              <textarea v-model="forms.text.text" class="form-control" rows="8"
                        placeholder="Paste your English text here..."></textarea>
            </div>
            <div class="mb-3">
              <label class="form-label">Language</label>
              <input v-model="forms.text.language" type="text" class="form-control" placeholder="en" />
            </div>
          </div>
        </div>
        <div class="modal-footer">
          <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>
          <button type="button" class="btn btn-primary" @click="submitImport" :disabled="importing" id="btn-submit-import">
            <span v-if="importing" class="spinner-border spinner-border-sm me-2"></span>
            Import
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { materialsApi } from '../api/index.js'
import { Modal } from 'bootstrap'

const router = useRouter()
const route = useRoute()
const materialType = computed(() => route.meta.materialType || 'main')
const isTemporary = computed(() => materialType.value === 'temporary')

const materials = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = 20
const loading = ref(false)
const importing = ref(false)
const importError = ref('')
const toast = ref(null)

const tabs = [
  { key: 'upload',      label: 'Upload File' },
  { key: 'url_media',   label: 'Media URL' },
  { key: 'url_article', label: 'Article URL' },
  { key: 'text',        label: 'Plain Text' },
]
const activeTab = ref('upload')

const forms = ref({
  upload:      { title: '', language: 'en', file: null },
  url_media:   { url: '', title: '', language: 'en' },
  url_article: { url: '', title: '', language: 'en' },
  text:        { title: '', text: '', language: 'en' },
})

async function load() {
  loading.value = true
  try {
    const res = await materialsApi.list(page.value, pageSize, materialType.value)
    materials.value = res.data.items
    total.value = res.data.total
  } finally {
    loading.value = false
  }
}

async function submitImport() {
  importError.value = ''
  importing.value = true
  try {
    const mt = materialType.value
    if (activeTab.value === 'upload') {
      const f = forms.value.upload
      if (!f.file) { importError.value = 'Please select a file'; importing.value = false; return }
      const fd = new FormData()
      fd.append('file', f.file)
      fd.append('title', f.title || f.file.name)
      fd.append('language', f.language)
      fd.append('material_type', mt)
      await materialsApi.uploadFile(fd)
    } else if (activeTab.value === 'url_media') {
      await materialsApi.importUrlMedia({ ...forms.value.url_media, material_type: mt })
    } else if (activeTab.value === 'url_article') {
      await materialsApi.importUrlArticle({ ...forms.value.url_article, material_type: mt })
    } else {
      if (!forms.value.text.title) { importError.value = 'Title is required'; importing.value = false; return }
      await materialsApi.importText({ ...forms.value.text, material_type: mt })
    }

    Modal.getInstance(document.getElementById('addModal'))?.hide()
    // Cleanup backdrop if it lingers
    document.querySelectorAll('.modal-backdrop').forEach(el => el.remove())
    document.body.classList.remove('modal-open')
    document.body.style.paddingRight = ''

    showToast('Material added! Processing will start shortly.', 'success')
    load()
  } catch (e) {
    importError.value = e.response?.data?.detail || 'Import failed'
  } finally {
    importing.value = false
  }
}

async function confirmDelete(m) {
  if (!confirm(`Delete "${m.title}"? The original file will be kept.`)) return
  try {
    await materialsApi.delete(m.id)
    showToast('Material deleted', 'warning')
    load()
  } catch (e) {
    showToast('Delete failed', 'danger')
  }
}

async function cleanupStorage(m) {
  if (!confirm(`Permanently delete all audio and video files for "${m.title}"? This cannot be undone.`)) return
  try {
    await materialsApi.deleteStorage(m.id)
    showToast('Storage cleaned up', 'success')
    load()
  } catch (e) {
    showToast('Cleanup failed', 'danger')
  }
}

async function reExecute(m) {
  if (!confirm(`Restart processing for "${m.title}"? Old results will be deleted.`)) return
  try {
    await materialsApi.reExecute(m.id)
    showToast('Processing restarted', 'success')
    load()
  } catch (e) {
    showToast('Restart failed', 'danger')
  }
}

function goDetail(id) {
  router.push(`/materials/${id}`)
}

function statusBadge(status) {
  const map = {
    pending:    'badge bg-secondary',
    processing: 'badge bg-warning text-dark',
    done:       'badge bg-success',
    failed:     'badge bg-danger',
  }
  return map[status] || 'badge bg-light text-dark'
}

function fmtDate(dt) {
  return new Date(dt).toLocaleString()
}

function showToast(msg, type = 'info') {
  toast.value = { message: msg, type }
  setTimeout(() => { toast.value = null }, 4000)
}

onMounted(load)
</script>

<style scoped>
.cursor-pointer { cursor: pointer; }
</style>
