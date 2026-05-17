<template>
  <div class="container py-4" style="max-width: 800px;">
    <h1 class="h4 mb-4">Admin</h1>

    <div class="alert alert-success" v-if="saved">Saved.</div>
    <div class="alert alert-danger" v-if="error">{{ error }}</div>

    <!-- Registration Toggles -->
    <div class="card mb-4 shadow-sm">
      <div class="card-header"><strong>Registration Settings</strong></div>
      <div class="card-body">
        <div class="form-check form-switch mb-3">
          <input class="form-check-input" type="checkbox" v-model="reg.registration_enabled"
                 id="toggle-reg" @change="saveReg" />
          <label class="form-check-label" for="toggle-reg">Registration Enabled</label>
          <div class="form-text">When off, no one can register.</div>
        </div>
        <div class="form-check form-switch mb-3">
          <input class="form-check-input" type="checkbox" v-model="reg.invite_verification_enabled"
                 id="toggle-invite" @change="saveReg" />
          <label class="form-check-label" for="toggle-invite">Invite Verification Required</label>
          <div class="form-text">When on, registration requires a valid invite code.</div>
        </div>
      </div>
    </div>

    <!-- STT Settings -->
    <div class="card mb-4 shadow-sm">
      <div class="card-header"><strong>STT Settings</strong></div>
      <div class="card-body">
        <div class="mb-3">
          <label class="form-label">STT Backend</label>
          <select class="form-select" v-model="stt.stt_backend" @change="saveStt" style="max-width: 300px;">
            <option value="api">API (SiliconFlow)</option>
            <option value="whisper_cpp">whisper_cpp_python (Local)</option>
          </select>
          <div class="form-text">Select which STT engine to use. "whisper_cpp" runs locally via whisper.cpp.</div>
        </div>
        <div class="mb-3">
          <label class="form-label">Max Consecutive Failures</label>
          <input v-model.number="stt.stt_max_consecutive_failures" type="number"
                 class="form-control" min="1" max="50" style="max-width: 150px;"
                 @change="saveStt" />
          <div class="form-text">Skip remaining STT segments after this many consecutive failures (default: 4).</div>
        </div>
        <div v-if="stt.stt_backend === 'whisper_cpp'">
          <!-- Package install check -->
          <div v-if="!stt.whisper_installed" class="alert alert-warning py-2 mb-3">
            <div class="d-flex align-items-center justify-content-between">
              <span><code>whisper-cpp-python</code> package is not installed.</span>
              <button class="btn btn-outline-warning btn-sm" @click="installPackage" :disabled="installing">
                <span v-if="installing" class="spinner-border spinner-border-sm me-1"></span>
                {{ installing ? 'Installing...' : 'Install Now' }}
              </button>
            </div>
            <div class="form-text mt-1">
              Or run manually: <code>uv sync --extra whisper</code>
            </div>
          </div>
          <div v-else-if="!stt.whisper_ready" class="alert alert-warning py-2 mb-3">
            <span><code>whisper-cpp-python</code> is installed but the shared library (<code>whisper.dll</code> / <code>libwhisper.so</code>) is missing.</span>
            <div class="form-text mt-1">The package needs a compiled whisper.cpp library. On Linux this is built automatically; on Windows ensure the build toolchain is available.</div>
          </div>
          <div class="mb-3">
            <label class="form-label">Whisper Model Path</label>
            <input v-model="stt.stt_whisper_model_path" type="text"
                   class="form-control" style="max-width: 400px;"
                   placeholder="auto-detected from download" @change="saveStt" />
            <div class="form-text">
              <span v-if="stt.model_exists" class="text-success">Model found on disk.</span>
              <span v-else class="text-warning">Model file not found. Download one below.</span>
            </div>
          </div>
          <div v-if="!stt.model_exists && stt.whisper_ready" class="card bg-light mb-3">
            <div class="card-body py-2">
              <div class="row g-2 align-items-end">
                <div class="col-auto">
                  <label class="form-label small">Model Size</label>
                  <select v-model="downloadSize" class="form-select form-select-sm" style="width: 140px;">
                    <option value="tiny">Tiny (~78 MB)</option>
                    <option value="base">Base (~148 MB)</option>
                    <option value="small">Small (~488 MB)</option>
                    <option value="medium">Medium (~1.5 GB)</option>
                    <option value="large">Large (~3.1 GB)</option>
                  </select>
                </div>
                <div class="col-auto">
                  <button class="btn btn-primary btn-sm" @click="downloadModel" :disabled="downloading">
                    <span v-if="downloading" class="spinner-border spinner-border-sm me-1"></span>
                    {{ downloading ? 'Downloading...' : 'Download Model' }}
                  </button>
                </div>
              </div>
              <div class="progress mt-2" v-if="downloadMsg" style="height: 6px;">
                <div class="progress-bar progress-bar-striped progress-bar-animated"
                     :style="{ width: downloadPct + '%' }"></div>
              </div>
              <div class="form-text mt-1" v-if="downloadMsg">{{ downloadMsg }}</div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Create Invite Code -->
    <div class="card mb-4 shadow-sm">
      <div class="card-header"><strong>Create Invite Code</strong></div>
      <div class="card-body">
        <div class="row g-3 align-items-end">
          <div class="col-auto">
            <label class="form-label">Max Uses (1-5)</label>
            <input v-model.number="newCode.max_uses" type="number" class="form-control"
                   min="1" max="5" style="width: 100px;" />
          </div>
          <div class="col-auto">
            <button type="button" class="btn btn-primary" @click="createCode" :disabled="creating">
              <span v-if="creating" class="spinner-border spinner-border-sm me-2"></span>
              Generate
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- All Invite Codes -->
    <div class="card shadow-sm">
      <div class="card-header"><strong>All Invite Codes</strong></div>
      <div class="card-body">
        <div v-if="codes.length === 0" class="text-muted">No invite codes.</div>
        <div v-else class="table-responsive">
          <table class="table table-sm table-bordered">
            <thead>
              <tr>
                <th>Code</th>
                <th>Created By</th>
                <th>Uses</th>
                <th>Created</th>
                <th>Expires</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="c in codes" :key="c.id">
                <td><code>{{ c.code }}</code></td>
                <td>{{ c.creator_user_id || 'Admin' }}</td>
                <td>{{ c.current_uses }} / {{ c.max_uses }}</td>
                <td>{{ new Date(c.created_at).toLocaleString() }}</td>
                <td>{{ c.expires_at ? new Date(c.expires_at).toLocaleString() : 'Never' }}</td>
                <td>
                  <span v-if="!c.is_active" class="text-danger">Used up</span>
                  <span v-else-if="c.expires_at && new Date(c.expires_at) < new Date()" class="text-danger">Expired</span>
                  <span v-else class="text-success">Active</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { adminApi } from '../api/index.js'

const reg = ref({
  registration_enabled: true,
  invite_verification_enabled: false,
})
const stt = ref({
  stt_backend: 'api',
  stt_max_consecutive_failures: 4,
  stt_whisper_model_path: '',
  model_exists: false,
  whisper_installed: false,
  whisper_ready: false,
})
const newCode = ref({ max_uses: 5 })
const codes = ref([])
const creating = ref(false)
const saved = ref(false)
const error = ref('')
const downloadSize = ref('base')
const downloading = ref(false)
const downloadMsg = ref('')
const downloadPct = ref(0)
const installing = ref(false)

async function loadReg() {
  try {
    const res = await adminApi.getRegistrationSettings()
    reg.value = res.data
  } catch {}
}

async function saveReg() {
  saved.value = false
  error.value = ''
  try {
    await adminApi.updateRegistrationSettings(reg.value)
    saved.value = true
    setTimeout(() => { saved.value = false }, 2000)
  } catch (e) {
    error.value = e.response?.data?.detail || 'Save failed'
  }
}

async function loadStt() {
  try {
    const res = await adminApi.getSttSettings()
    stt.value = res.data
  } catch {}
}

async function saveStt() {
  saved.value = false
  error.value = ''
  try {
    await adminApi.updateSttSettings(stt.value)
    saved.value = true
    setTimeout(() => { saved.value = false }, 2000)
  } catch (e) {
    error.value = e.response?.data?.detail || 'Save failed'
  }
}

async function loadCodes() {
  try {
    const res = await adminApi.listInviteCodes()
    codes.value = res.data
  } catch {}
}

async function installPackage() {
  installing.value = true
  error.value = ''
  try {
    const res = await adminApi.installWhisperPackage()
    stt.value = res.data
    saved.value = true
    setTimeout(() => { saved.value = false }, 2000)
  } catch (e) {
    error.value = e.response?.data?.detail || 'Install failed'
  } finally {
    installing.value = false
  }
}

async function downloadModel() {
  downloading.value = true
  downloadMsg.value = 'Starting download...'
  downloadPct.value = 0
  error.value = ''
  try {
    const res = await adminApi.downloadWhisperModel(downloadSize.value)
    stt.value = res.data
    downloadMsg.value = ''
    saved.value = true
    setTimeout(() => { saved.value = false }, 2000)
  } catch (e) {
    error.value = e.response?.data?.detail || 'Download failed'
    downloadMsg.value = ''
  } finally {
    downloading.value = false
  }
}

async function createCode() {
  creating.value = true
  error.value = ''
  try {
    await adminApi.createInviteCode({ max_uses: newCode.value.max_uses })
    await loadCodes()
  } catch (e) {
    error.value = e.response?.data?.detail || 'Failed to create code'
  } finally {
    creating.value = false
  }
}

onMounted(() => {
  loadReg()
  loadStt()
  loadCodes()
})
</script>
