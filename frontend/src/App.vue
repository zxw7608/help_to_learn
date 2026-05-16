<template>
  <nav class="navbar navbar-expand-lg navbar-dark bg-dark" v-if="authStore.isLoggedIn">
    <div class="container-fluid">
      <a class="navbar-brand" href="#">
        <strong>📚 EL Manager</strong>
      </a>
      <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarNav">
        <span class="navbar-toggler-icon"></span>
      </button>
      <div class="collapse navbar-collapse" id="navbarNav">
        <ul class="navbar-nav me-auto">
          <li class="nav-item">
            <RouterLink class="nav-link" to="/materials">Materials</RouterLink>
          </li>
          <li class="nav-item">
            <RouterLink class="nav-link" to="/materials/temporary">Temporary</RouterLink>
          </li>
          <li class="nav-item">
            <RouterLink class="nav-link" to="/settings">Settings</RouterLink>
          </li>
          <li class="nav-item" v-if="authStore.isAdmin">
            <RouterLink class="nav-link" to="/admin">Admin</RouterLink>
          </li>
        </ul>
        <ul class="navbar-nav">
          <li class="nav-item">
            <span class="navbar-text me-3 text-light">{{ authStore.username }}</span>
          </li>
          <li class="nav-item">
            <button class="btn btn-sm btn-outline-light" @click="logout">Logout</button>
          </li>
        </ul>
      </div>
    </div>
  </nav>

  <RouterView />
</template>

<script setup>
import { RouterLink, RouterView, useRouter } from 'vue-router'
import { useAuthStore } from './stores/auth.js'

const authStore = useAuthStore()
const router = useRouter()

function logout() {
  authStore.logout()
  router.push('/login')
}
</script>
