<template>
  <div class="min-vh-100 d-flex align-items-center justify-content-center bg-light">
    <div class="card shadow-sm" style="width: 380px;">
      <div class="card-body p-4">
        <h1 class="h4 card-title text-center mb-4">📚 English Learning Manager</h1>
        <h2 class="h6 text-muted text-center mb-4">Sign In</h2>

        <div class="alert alert-danger" v-if="error">{{ error }}</div>

        <form @submit.prevent="submit">
          <div class="mb-3">
            <label class="form-label" for="username">Username</label>
            <input id="username" v-model="form.username" type="text" class="form-control"
                   placeholder="Enter username" required autocomplete="username" />
          </div>
          <div class="mb-3">
            <label class="form-label" for="password">Password</label>
            <input id="password" v-model="form.password" type="password" class="form-control"
                   placeholder="Enter password" required autocomplete="current-password" />
          </div>
          <button type="submit" class="btn btn-primary w-100" :disabled="loading">
            <span v-if="loading" class="spinner-border spinner-border-sm me-2"></span>
            Sign In
          </button>
        </form>

        <p class="text-center mt-3 mb-0 small">
          No account? <RouterLink to="/register">Register</RouterLink>
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

const form = ref({ username: '', password: '' })
const error = ref('')
const loading = ref(false)

async function submit() {
  error.value = ''
  loading.value = true
  try {
    const res = await authApi.login(form.value)
    authStore.setTokens(res.data.access_token, res.data.refresh_token)
    // Fetch user info for admin status
    try {
      const me = await usersApi.me()
      authStore.setUser(me.data.username, me.data.is_admin)
    } catch {}
    router.push('/materials')
  } catch (e) {
    error.value = e.response?.data?.detail || 'Login failed'
  } finally {
    loading.value = false
  }
}
</script>
