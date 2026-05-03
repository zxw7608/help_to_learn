<template>
  <div class="container py-4" style="max-width: 800px;">
    <div class="d-flex align-items-center mb-4 gap-3">
      <RouterLink to="/materials" class="btn btn-back">← Back</RouterLink>
      <h1 class="h4 mb-0">AI 解析记录</h1>
    </div>

    <div v-if="loading" class="text-center py-5">
      <div class="spinner-border text-primary"></div>
    </div>

    <div v-else-if="!records.length" class="text-center py-5 text-muted">
      暂无 AI 解析记录
    </div>

    <div v-for="rec in records" :key="rec.id" class="card mb-3 shadow-sm">
      <div class="card-body">
        <div class="d-flex justify-content-between align-items-start mb-2">
          <div>
            <RouterLink v-if="rec.material_id" :to="`/materials/${rec.material_id}`" class="text-decoration-none">
              <span class="badge bg-secondary me-2">{{ rec.material_title || '未知材料' }}</span>
            </RouterLink>
            <span class="badge bg-light text-dark">片段 #{{ rec.segment_index }}</span>
          </div>
          <small class="text-muted">{{ new Date(rec.created_at).toLocaleString() }}</small>
        </div>

        <div class="segment-context mb-3">
          <small class="text-muted">原文: {{ rec.segment_text }}</small>
        </div>

        <p class="mb-2">
          <strong>选中短语:</strong>
          <span class="text-primary">{{ rec.selected_phrase }}</span>
        </p>

        <div class="analysis-content" v-html="formatAnalysis(rec.analysis)"></div>
      </div>
    </div>

    <div class="d-flex justify-content-center gap-3 mt-3" v-if="totalPages > 1">
      <button class="btn btn-outline-secondary btn-sm" @click="goPage(page - 1)" :disabled="page <= 1">上一页</button>
      <span class="align-self-center text-muted">{{ page }} / {{ totalPages }}</span>
      <button class="btn btn-outline-secondary btn-sm" @click="goPage(page + 1)" :disabled="page >= totalPages">下一页</button>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { analysisApi } from '../api/index.js'

const records = ref([])
const loading = ref(false)
const page = ref(1)
const totalPages = ref(1)
const pageSize = 20

function formatAnalysis(text) {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\n/g, '<br>')
}

async function loadRecords() {
  loading.value = true
  try {
    const res = await analysisApi.list(page.value, pageSize)
    records.value = res.data
    // If fewer results than pageSize, this is the last page
    if (res.data.length < pageSize) {
      totalPages.value = page.value
    } else {
      totalPages.value = page.value + 1 // there might be more
    }
  } catch {
    records.value = []
    totalPages.value = 1
  } finally {
    loading.value = false
  }
}

function goPage(p) {
  page.value = p
  loadRecords()
}

onMounted(loadRecords)
</script>

<style scoped>
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

.segment-context {
  font-style: italic;
  padding: 8px 12px;
  background: #f8f9fa;
  border-radius: 6px;
  border-left: 3px solid #dee2e6;
}

.analysis-content {
  font-size: 0.9rem;
  line-height: 1.7;
  color: #343a40;
  white-space: pre-line;
  padding: 12px;
  background: #f0f7ff;
  border-radius: 8px;
}
</style>
