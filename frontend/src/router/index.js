import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth.js'

const routes = [
  { path: '/', redirect: '/materials' },
  { path: '/login',    component: () => import('../views/Login.vue'),          meta: { guest: true } },
  { path: '/register', component: () => import('../views/Register.vue'),       meta: { guest: true } },
  { path: '/materials',          component: () => import('../views/Materials.vue'),      meta: { auth: true } },
  { path: '/materials/temporary', component: () => import('../views/Materials.vue'),      meta: { auth: true, materialType: 'temporary' } },
  { path: '/materials/:id',      component: () => import('../views/MaterialDetail.vue'), meta: { auth: true } },
  { path: '/settings',           component: () => import('../views/Settings.vue'),       meta: { auth: true } },
  { path: '/analysis-records',  component: () => import('../views/AnalysisRecords.vue'), meta: { auth: true } },
  // Public share page — no auth required
  { path: '/share/:id',          component: () => import('../views/ShareView.vue') },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to) => {
  const auth = useAuthStore()
  if (to.meta.auth && !auth.isLoggedIn) return '/login'
  if (to.meta.guest && auth.isLoggedIn)  return '/materials'
})

export default router
