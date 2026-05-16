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
const newCode = ref({ max_uses: 5 })
const codes = ref([])
const creating = ref(false)
const saved = ref(false)
const error = ref('')

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

async function loadCodes() {
  try {
    const res = await adminApi.listInviteCodes()
    codes.value = res.data
  } catch {}
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
  loadCodes()
})
</script>
