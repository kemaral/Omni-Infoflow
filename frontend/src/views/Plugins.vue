<template>
  <div>
    <div class="page-header">
      <h2>🧩 Plugins</h2>
      <p>管理和配置所有已注册的插件模块</p>
    </div>

    <div v-if="loadError" class="card" style="margin-bottom: 16px; border-color: var(--warning);">
      <div class="text-sm" style="color: var(--warning);">{{ loadError }}</div>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="text-muted" style="padding: 40px; text-align: center;">
      正在发现插件...
    </div>

    <!-- Plugin Cards -->
    <div v-else class="card-grid">
      <div
        v-for="plugin in plugins"
        :key="plugin.name"
        class="card"
        :style="plugin.error ? 'opacity: 0.5' : ''"
      >
        <div class="card-header">
          <div>
            <div class="card-title">{{ plugin.name }}</div>
            <div class="text-sm text-muted mt-16" style="margin-top: 4px;">
              v{{ plugin.version || '?' }}
            </div>
          </div>
          <span class="card-badge" :class="'badge-' + plugin.category">
            {{ plugin.category }}
          </span>
        </div>

        <p class="text-sm text-muted" style="margin-bottom: 16px;">
          {{ plugin.description || plugin.error || '无描述' }}
        </p>

        <!-- Enable toggle -->
        <div class="flex items-center justify-between mb-16">
          <span class="text-sm">启用</span>
          <label class="toggle">
            <input
              type="checkbox"
              :checked="plugin.enabled"
              @change="togglePlugin(plugin)"
            />
            <span class="toggle-slider"></span>
          </label>
        </div>

        <!-- Config Schema Auto-rendering -->
        <div v-if="plugin.config_schema && Object.keys(plugin.config_schema).length > 0">
          <div class="text-sm" style="font-weight: 600; margin-bottom: 12px; color: var(--text-secondary);">
            参数配置
          </div>
          <div
            v-for="(schema, key) in plugin.config_schema"
            :key="key"
            class="form-group"
          >
            <label class="form-label">{{ key }}</label>

            <!-- List type -->
            <textarea
              v-if="schema.type === 'list'"
              class="form-textarea"
              :placeholder="schema.description"
              :value="getPluginConfigValue(plugin, key)"
              @input="setPluginConfigValue(plugin, key, $event.target.value)"
              rows="3"
            ></textarea>

            <!-- Number / int / float -->
            <input
              v-else-if="schema.type === 'int' || schema.type === 'float'"
              type="number"
              class="form-input"
              :placeholder="schema.default ?? ''"
              :value="getPluginConfigValue(plugin, key)"
              @input="setPluginConfigValue(plugin, key, $event.target.value)"
            />

            <!-- String (default) -->
            <input
              v-else
              type="text"
              class="form-input"
              :placeholder="schema.default ?? ''"
              :value="getPluginConfigValue(plugin, key)"
              @input="setPluginConfigValue(plugin, key, $event.target.value)"
            />

            <div class="form-hint" v-if="schema.description">
              {{ schema.description }}
              <span v-if="schema.required" style="color: var(--error);">*必填</span>
            </div>
          </div>
        </div>

        <!-- Save button -->
        <button
          class="btn btn-primary btn-sm mt-16"
          style="width: 100%;"
          @click="savePlugin(plugin)"
        >
          💾 保存配置
        </button>
      </div>
    </div>

    <!-- Save All -->
    <div class="mt-24" v-if="plugins.length > 0">
      <button class="btn btn-success" @click="saveAll">
        ✅ 保存全部配置
      </button>
      <span class="text-sm text-muted" style="margin-left: 12px;" v-if="saveMsg">
        {{ saveMsg }}
      </span>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { api } from '../api/client.js'

const plugins = ref([])
const loading = ref(true)
const config = ref({})
const saveMsg = ref('')
const editedConfigs = ref({})
const loadError = ref('')

async function loadPlugins() {
  loading.value = true
  loadError.value = ''
  try {
    const [discovered, cfg] = await Promise.all([
      api.discoverPlugins(),
      api.getConfig(),
    ])
    plugins.value = discovered
    config.value = cfg
    // Pre-populate edited configs from current config
    for (const category of Object.keys(cfg.plugins || {})) {
      for (const entry of cfg.plugins[category]) {
        // Match by class path
        const key = entry.class
        if (key) {
          editedConfigs.value[key] = { ...(entry.config || {}) }
        }
      }
    }
  } catch (e) {
    console.error('Failed to load plugins:', e)
    loadError.value = e.status === 401
      ? '需要管理员令牌才能读取插件配置，请先在侧栏保存 Admin Token。'
      : '插件加载失败，请检查后端服务或配置。'
  }
  loading.value = false
}

function getPluginConfigValue(plugin, key) {
  const classPath = plugin.class
  const edited = editedConfigs.value[classPath]
  if (edited && key in edited) {
    const val = edited[key]
    return Array.isArray(val) ? val.join('\n') : val
  }
  const schema = plugin.config_schema?.[key]
  const def = schema?.default
  return Array.isArray(def) ? def.join('\n') : (def ?? '')
}

function setPluginConfigValue(plugin, key, value) {
  const classPath = plugin.class
  if (!editedConfigs.value[classPath]) {
    editedConfigs.value[classPath] = {}
  }
  const schema = plugin.config_schema?.[key]
  if (schema?.type === 'list') {
    editedConfigs.value[classPath][key] = value.split('\n').filter(Boolean)
  } else if (schema?.type === 'int') {
    editedConfigs.value[classPath][key] = parseInt(value) || 0
  } else if (schema?.type === 'float') {
    editedConfigs.value[classPath][key] = parseFloat(value) || 0
  } else {
    editedConfigs.value[classPath][key] = value
  }
}

async function togglePlugin(plugin) {
  plugin.enabled = !plugin.enabled
  await savePlugin(plugin)
}

async function savePlugin(plugin) {
  // Find and update the plugin entry in config
  const category = findCategory(plugin.category)
  if (!category) return

  if (!config.value.plugins) {
    config.value.plugins = {}
  }
  if (!config.value.plugins[category]) {
    config.value.plugins[category] = []
  }

  const entries = config.value.plugins?.[category] || []
  let entry = entries.find(e => e.class === plugin.class)
  if (!entry) {
    entry = {
      class: plugin.class,
      enabled: plugin.enabled,
      config: editedConfigs.value[plugin.class] || {},
    }
    entries.push(entry)
  }
  if (entry) {
    entry.enabled = plugin.enabled
    entry.config = editedConfigs.value[plugin.class] || entry.config
  }

  await saveAll()
}

async function saveAll() {
  try {
    await api.patchConfig({ plugins: config.value.plugins })
    saveMsg.value = '✅ 已保存'
    setTimeout(() => saveMsg.value = '', 3000)
  } catch (e) {
    saveMsg.value = '❌ 保存失败: ' + e.message
  }
}

function findCategory(pluginCategory) {
  const map = {
    source: 'sources',
    parser: 'parsers',
    ai: 'ai',
    media: 'media',
    dispatcher: 'dispatchers',
  }
  return map[pluginCategory] || null
}

onMounted(loadPlugins)
</script>
