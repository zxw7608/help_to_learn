<template>
  <div class="container py-4" style="max-width: 700px;">
    <h1 class="h4 mb-4">Settings</h1>

    <div class="alert alert-success" v-if="saved">Settings saved successfully.</div>
    <div class="alert alert-danger" v-if="error">{{ error }}</div>

    <form @submit.prevent="save">
      <!-- Anki -->
      <div class="card mb-4 shadow-sm">
        <div class="card-header"><strong>🃏 Anki</strong></div>
        <div class="card-body">
          <div class="mb-3">
            <label class="form-label">Deck Name</label>
            <input v-model="form.anki_deck_name" type="text" class="form-control"
                   placeholder="English::Listening" id="input-anki-deck" />
            <div class="form-text">Make sure this deck exists in Anki or it will be created.</div>
          </div>
          <div class="mb-3">
            <label class="form-label">Note Model Name</label>
            <input v-model="form.anki_model_name" type="text" class="form-control"
                   placeholder="Basic" id="input-anki-model" />
            <div class="form-text">Note type (e.g., Basic, Basic (and reversed card)). <strong>Must exist</strong> in your Anki collection.</div>
          </div>
          <div class="mb-3">
            <label class="form-label">AnkiConnect URL</label>
            <input v-model="form.anki_connect_url" type="url" class="form-control"
                   placeholder="http://127.0.0.1:8765" id="input-anki-url" />
            <div class="form-text">Address of your Anki desktop with AnkiConnect. Use <code>http://&lt;IP&gt;:8765</code> for LAN access.</div>
          </div>
        </div>
      </div>

      <!-- Telegram -->
      <div class="card mb-4 shadow-sm">
        <div class="card-header"><strong>✈️ Telegram</strong></div>
        <div class="card-body">
          <div class="mb-3">
            <label class="form-label">Bot Token (Optional)</label>
            <input v-model="form.telegram_bot_token" type="password" class="form-control"
                   placeholder="Leave empty to use server default" id="input-telegram-token" />
            <div class="form-text">Set this if you want to use your own Telegram bot.</div>
          </div>
          <div class="mb-3">
            <label class="form-label">Your Chat ID</label>
            <input v-model="form.telegram_chat_id" type="text" class="form-control"
                   placeholder="e.g. 123456789" id="input-telegram-chat" />
            <div class="form-text">
              Send /start to your bot, then get the Chat ID from
              <code>https://api.telegram.org/bot&lt;TOKEN&gt;/getUpdates</code>.
            </div>
          </div>
        </div>
      </div>

      <!-- AI -->
      <div class="card mb-4 shadow-sm">
        <div class="card-header"><strong>🤖 AI 解析</strong></div>
        <div class="card-body">
          <div class="mb-3">
            <label class="form-label">API Base URL</label>
            <input v-model="form.ai_base_url" type="url" class="form-control"
                   placeholder="https://api.openai.com/v1" id="input-ai-base-url" />
            <div class="form-text">OpenAI-compatible API base URL (e.g., https://api.openai.com/v1, https://api.siliconflow.cn/v1).</div>
          </div>
          <div class="mb-3">
            <label class="form-label">Model</label>
            <input v-model="form.ai_model" type="text" class="form-control"
                   placeholder="gpt-3.5-turbo" id="input-ai-model" />
            <div class="form-text">Model name (e.g., gpt-3.5-turbo, gpt-4o, deepseek-chat).</div>
          </div>
          <div class="mb-3">
            <label class="form-label">API Key</label>
            <input v-model="form.ai_api_key" type="password" class="form-control"
                   placeholder="sk-..." id="input-ai-api-key" />
            <div class="form-text">Your API key for the above service.</div>
          </div>
          <div class="mb-3">
            <label class="form-label">Prompt 模板</label>
            <textarea v-model="form.ai_prompt" class="form-control" rows="10"
                      placeholder="留空则使用默认中文解析模板..." id="input-ai-prompt"
                      style="font-size: 0.8rem; font-family: monospace;"></textarea>
            <div class="form-text">
              可用变量: <code>$\{phrase\}</code> <code>$\{immediateContext\}</code> <code>$\{contextStr\}</code>
              留空则使用默认中文解析模板。
            </div>
          </div>
        </div>
      </div>

      <!-- TTS / STT -->
      <div class="card mb-4 shadow-sm">
        <div class="card-header"><strong>🔊 TTS / STT Worker</strong></div>
        <div class="card-body">
          <div class="mb-3">
            <label class="form-label">Worker URL</label>
            <input v-model="form.tts_worker_url" type="url" class="form-control"
                   placeholder="https://your-worker.workers.dev" id="input-tts-url" />
            <div class="form-text">Your deployed wangwangit/tts Cloudflare Worker URL.</div>
          </div>
          <div class="mb-3">
            <label class="form-label">SiliconFlow Token (for STT)</label>
            <input v-model="form.tts_token" type="password" class="form-control"
                   placeholder="Leave empty to use server default" id="input-tts-token" />
          </div>
        </div>
      </div>

      <button type="submit" class="btn btn-primary" :disabled="saving" id="btn-save-settings">
        <span v-if="saving" class="spinner-border spinner-border-sm me-2"></span>
        Save Settings
      </button>
    </form>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { usersApi } from '../api/index.js'

const form = ref({
  anki_deck_name: '',
  anki_model_name: '',
  anki_connect_url: '',
  telegram_chat_id: '',
  telegram_bot_token: '',
  ai_base_url: '',
  ai_api_key: '',
  ai_model: '',
  ai_prompt: '',
  tts_worker_url: '',
  tts_token: '',
})
const saving = ref(false)
const saved = ref(false)
const error = ref('')

async function load() {
  try {
    const res = await usersApi.me()
    const u = res.data
    form.value = {
      anki_deck_name:     u.anki_deck_name || 'English::Listening',
      anki_model_name:    u.anki_model_name || 'Basic',
      anki_connect_url:   u.anki_connect_url || 'http://127.0.0.1:8765',
      telegram_chat_id:   u.telegram_chat_id || '',
      telegram_bot_token: '', // Sensitive
      ai_base_url:        u.ai_base_url || '',
      ai_api_key:         '', // Sensitive
      ai_model:           u.ai_model || '',
      ai_prompt:          u.ai_prompt || '',
      tts_worker_url:     u.tts_worker_url || '',
      tts_token:          '', // Sensitive
    }
  } catch {}
}

async function save() {
  saving.value = true
  saved.value = false
  error.value = ''
  try {
    const payload = { ...form.value }
    if (!payload.tts_token) delete payload.tts_token
    if (!payload.telegram_bot_token) delete payload.telegram_bot_token
    if (!payload.ai_api_key) delete payload.ai_api_key
    await usersApi.update(payload)
    saved.value = true
    setTimeout(() => { saved.value = false }, 3000)
  } catch (e) {
    error.value = e.response?.data?.detail || 'Save failed'
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>
