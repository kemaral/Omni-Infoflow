<template>
  <div>
    <div class="page-header">
      <h2>Dashboard</h2>
      <p>实时监控工作流执行状态与日志</p>
    </div>

    <!-- Stats Row -->
    <div class="stats-row">
      <div class="stat-card">
        <div class="stat-value">{{ status.processed_items_count ?? 0 }}</div>
        <div class="stat-label">已处理条目</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{{ status.event_buffer_size ?? 0 }}</div>
        <div class="stat-label">事件缓冲</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{{ status.active_runs ?? 0 }}</div>
        <div class="stat-label">活跃运行</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{{ events.length }}</div>
        <div class="stat-label">日志条目</div>
      </div>
    </div>

    <!-- Controls -->
    <div class="flex items-center justify-between mb-16">
      <div class="flex gap-8">
        <button class="btn btn-primary" @click="triggerRun" :disabled="running">
          {{ running ? '⏳ 运行中...' : '▶️ 触发工作流' }}
        </button>
        <button class="btn btn-secondary" @click="refreshLogs">
          🔄 刷新日志
        </button>
      </div>
      <div class="flex items-center gap-8">
        <label class="toggle">
          <input type="checkbox" v-model="autoStream" @change="toggleStream" />
          <span class="toggle-slider"></span>
        </label>
        <span class="text-sm text-muted">实时推送</span>
      </div>
    </div>
    <div v-if="msg" class="text-sm text-muted mb-16">{{ msg }}</div>

    <!-- Event Log -->
    <div class="card" style="padding: 16px;">
      <div class="event-list" ref="logContainer">
        <div v-if="events.length === 0" class="text-muted text-sm" style="padding: 24px; text-align: center;">
          暂无事件日志 — 触发工作流或开启实时推送
        </div>
        <div
          v-for="(evt, i) in events"
          :key="i"
          class="event-item"
          :class="'status-' + evt.status"
        >
          <span class="event-time">{{ formatTime(evt.timestamp) }}</span>
          <span class="event-step">{{ evt.step }}</span>
          <span class="event-plugin">{{ evt.plugin_name }}</span>
          <span class="event-msg">
            <span :class="'badge-status-' + evt.status">{{ evt.status }}</span>
            {{ evt.message }}
            <span v-if="evt.duration_ms" class="mono text-muted">
              ({{ evt.duration_ms }}ms)
            </span>
          </span>
        </div>
      </div>
    </div>

    <!-- Recent Items Table -->
    <div class="mt-24">
      <h3 style="margin-bottom: 16px;">📋 已处理条目</h3>
      <div class="card" style="padding: 0; overflow: hidden;">
        <table class="data-table">
          <thead>
            <tr>
              <th>标题</th>
              <th>来源</th>
              <th>状态</th>
              <th>时间</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="items.length === 0">
              <td colspan="4" style="text-align: center; padding: 24px;" class="text-muted">
                暂无已处理条目
              </td>
            </tr>
            <tr v-for="item in items" :key="item.id">
              <td>{{ item.title || '—' }}</td>
              <td class="mono text-sm">{{ item.source_type }}</td>
              <td>
                <span class="card-badge" :class="item.status === 'completed' ? 'badge-parser' : 'badge-dispatcher'">
                  {{ item.status }}
                </span>
              </td>
              <td class="text-muted text-sm">{{ item.created_at?.slice(0, 19) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, nextTick } from 'vue'
import { api } from '../api/client.js'

const status = ref({})
const events = ref([])
const items = ref([])
const running = ref(false)
const autoStream = ref(false)
const logContainer = ref(null)
const msg = ref('')
let eventSource = null
let statusTimer = null

async function refreshStatus() {
  try { status.value = await api.getStatus() } catch {}
}

async function refreshLogs() {
  try { events.value = await api.getLogs(100) } catch {}
}

async function refreshItems() {
  try { items.value = await api.getItems(30) } catch {}
}

async function triggerRun() {
  running.value = true
  msg.value = ''
  try {
    await api.triggerRun()
    msg.value = '✅ 已触发工作流'
    // Wait a bit then refresh
    setTimeout(async () => {
      await refreshLogs()
      await refreshItems()
      await refreshStatus()
      running.value = false
    }, 3000)
  } catch (e) {
    msg.value = e.status === 401 ? '❌ 缺少或无效 Admin Token' : '❌ 触发失败: ' + e.message
    running.value = false
  }
}

function toggleStream() {
  if (autoStream.value) {
    eventSource = api.streamLogs()
    eventSource.onmessage = async (e) => {
      try {
        const data = JSON.parse(e.data)
        if (data.type === 'connected') return
        events.value.push(data)
        // Keep only last 200
        if (events.value.length > 200) events.value = events.value.slice(-200)
        await nextTick()
        if (logContainer.value) {
          logContainer.value.scrollTop = logContainer.value.scrollHeight
        }
      } catch {}
    }
    eventSource.onerror = () => {
      autoStream.value = false
      eventSource?.close()
    }
  } else {
    eventSource?.close()
    eventSource = null
  }
}

function formatTime(ts) {
  if (!ts) return ''
  const d = new Date(ts)
  return d.toLocaleTimeString('zh-CN', { hour12: false })
}

onMounted(() => {
  refreshStatus()
  refreshLogs()
  refreshItems()
  statusTimer = setInterval(() => {
    refreshStatus()
    refreshItems()
  }, 10000)
})

onUnmounted(() => {
  if (statusTimer) clearInterval(statusTimer)
  eventSource?.close()
})
</script>
