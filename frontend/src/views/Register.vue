<template>
  <div class="min-vh-100 d-flex align-items-center justify-content-center bg-light">
    <div class="card shadow-sm" style="width: 400px;">
      <div class="card-body p-4">
        <h1 class="h4 card-title text-center mb-4">📚 English Learning Manager</h1>
        <h2 class="h6 text-muted text-center mb-4">Create Account</h2>

        <div class="alert alert-danger" v-if="error">{{ error }}</div>
        <div class="alert alert-success" v-if="success">{{ success }}</div>

        <form @submit.prevent="submit">
          <div class="mb-3">
            <label class="form-label" for="reg-username">Username</label>
            <input id="reg-username" v-model="form.username" type="text" class="form-control" required />
          </div>
          <div class="mb-3">
            <label class="form-label" for="reg-email">Email</label>
            <input id="reg-email" v-model="form.email" type="email" class="form-control" required />
          </div>
          <div class="mb-3">
            <label class="form-label" for="reg-password">Password</label>
            <input id="reg-password" v-model="form.password" type="password" class="form-control" required minlength="6" />
          </div>
          <div class="mb-3">
            <label class="form-label" for="reg-invite">Invite Code (may be required)</label>
            <input id="reg-invite" v-model="form.invite_code" type="text" class="form-control" placeholder="Leave empty if not required" />
          </div>
          <button type="submit" class="btn btn-success w-100" :disabled="loading">
            <span v-if="loading" class="spinner-border spinner-border-sm me-2"></span>
            Register
          </button>
        </form>

        <p class="text-center mt-3 mb-0 small">
          Already have an account? <RouterLink to="/login">Sign in</RouterLink>
        </p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { authApi, usersApi } from '../api/index.js'
import { useAuthStore } from '../stores/auth.js'

const router = useRouter()
const authStore = useAuthStore()

const form = ref({ username: '', email: '', password: '', invite_code: '' })
const error = ref('')
const success = ref('')
const loading = ref(false)

async function submit() {
  error.value = ''
  success.value = ''
  loading.value = true
  try {
    const payload = { ...form.value }
    if (!payload.invite_code) delete payload.invite_code
    const res = await authApi.register(payload)
    authStore.setTokens(res.data.access_token, res.data.refresh_token)
    // Fetch user info for admin status (first user is auto-admin)
    try {
      const me = await usersApi.me()
      authStore.setUser(me.data.username, me.data.is_admin)
    } catch {}
    router.push('/materials')
  } catch (e) {
    error.value = e.response?.data?.detail || 'Registration failed'
  } finally {
    loading.value = false
  }
}
</script>
