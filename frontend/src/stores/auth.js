import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export const useAuthStore = defineStore('auth', () => {
  const accessToken  = ref(localStorage.getItem('access_token') || null)
  const refreshToken = ref(localStorage.getItem('refresh_token') || null)
  const username     = ref(localStorage.getItem('username') || null)
  const isAdmin      = ref(localStorage.getItem('is_admin') === 'true')

  const isLoggedIn = computed(() => !!accessToken.value)

  function setTokens(access, refresh) {
    accessToken.value  = access
    refreshToken.value = refresh
    localStorage.setItem('access_token',  access)
    localStorage.setItem('refresh_token', refresh)
  }

  function setUser(name, admin) {
    username.value = name
    isAdmin.value = !!admin
    localStorage.setItem('username', name)
    localStorage.setItem('is_admin', admin ? 'true' : 'false')
  }

  function setUsername(name) {
    username.value = name
    localStorage.setItem('username', name)
  }

  function logout() {
    accessToken.value  = null
    refreshToken.value = null
    username.value     = null
    isAdmin.value      = false
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
    localStorage.removeItem('username')
    localStorage.removeItem('is_admin')
  }

  return { accessToken, refreshToken, username, isAdmin, isLoggedIn, setTokens, setUsername, setUser, logout }
})
