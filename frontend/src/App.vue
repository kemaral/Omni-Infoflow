<template>
  <div class="app-shell">
    <aside class="sidebar">
      <div class="sidebar-logo">
        <h1>Omni-InfoFlow</h1>
        <div class="subtitle">Processing Engine</div>
      </div>

      <nav>
        <router-link to="/dashboard" class="nav-item">
          <span class="nav-icon">📊</span>
          Dashboard
        </router-link>
        <router-link to="/plugins" class="nav-item">
          <span class="nav-icon">🧩</span>
          Plugins
        </router-link>
        <router-link to="/setup" class="nav-item">
          <span class="nav-icon">⚙️</span>
          Setup
        </router-link>
      </nav>

      <div class="sidebar-footer">
        <div class="sidebar-status">
          <span class="status-dot"></span>
          <span class="text-sm text-muted">
            {{ status.processed_items_count ?? '—' }} items processed
          </span>
        </div>
        <div class="auth-panel">
          <label class="form-label" for="admin-token">Admin Token</label>
          <input
            id="admin-token"
            v-model="adminToken"
            class="form-input"
            type="password"
            placeholder="Optional for protected APIs"
          />
          <div class="auth-actions">
            <button class="btn btn-primary btn-sm" @click="saveAdminToken">
              Save
            </button>
            <button class="btn btn-secondary btn-sm" @click="clearAdminToken">
              Clear
            </button>
          </div>
          <div class="form-hint">
            Stored only in this browser and sent as `X-Omniflow-Admin-Token`.
          </div>
          <div v-if="authMessage" class="auth-message text-sm text-muted">
            {{ authMessage }}
          </div>
        </div>
      </div>
    </aside>

    <main class="main-content">
      <router-view />
    </main>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { api, getAdminToken, setAdminToken } from './api/client.js'

const status = ref({})
const adminToken = ref(getAdminToken())
const authMessage = ref('')
let timer = null

async function pollStatus() {
  try {
    status.value = await api.getStatus()
  } catch (e) {
    /* server might not be up yet */
  }
}

onMounted(() => {
  pollStatus()
  timer = setInterval(pollStatus, 5000)
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
})

function saveAdminToken() {
  setAdminToken(adminToken.value)
  authMessage.value = adminToken.value.trim()
    ? 'Admin token saved locally. Reload protected views if needed.'
    : 'Admin token removed.'
}

function clearAdminToken() {
  adminToken.value = ''
  setAdminToken('')
  authMessage.value = 'Admin token removed.'
}
</script>
