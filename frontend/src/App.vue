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
        <span class="status-dot"></span>
        <span class="text-sm text-muted">
          {{ status.processed_items_count ?? '—' }} items processed
        </span>
        <div class="text-sm text-muted mt-16">
          scheduler: {{ status.scheduler_enabled ? 'on' : 'off' }}
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
import { api } from './api/client.js'

const status = ref({})
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
</script>
