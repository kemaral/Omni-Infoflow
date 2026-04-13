<template>
  <div>
    <div class="page-header">
      <h2>⚙️ Setup</h2>
      <p>全局环境配置与工作流策略管理</p>
    </div>

    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 24px;">

      <!-- Global Settings -->
      <div class="card">
        <div class="card-header">
          <span class="card-title">🌐 全局设置</span>
        </div>
        <div class="form-group">
          <label class="form-label">项目名称</label>
          <input
            class="form-input"
            v-model="form.global.project_name"
            placeholder="Omni-InfoFlow"
          />
        </div>
        <div class="form-group">
          <label class="form-label">日志级别</label>
          <select class="form-select" v-model="form.global.log_level">
            <option value="DEBUG">DEBUG</option>
            <option value="INFO">INFO</option>
            <option value="WARNING">WARNING</option>
            <option value="ERROR">ERROR</option>
          </select>
        </div>
      </div>

      <!-- Workflow Policy -->
      <div class="card">
        <div class="card-header">
          <span class="card-title">🔄 工作流策略</span>
        </div>
        <div class="form-group">
          <label class="form-label">处理步骤 (逗号分隔)</label>
          <input
            class="form-input mono"
            :value="form.workflow.steps?.join(', ')"
            @input="form.workflow.steps = $event.target.value.split(',').map(s => s.trim()).filter(Boolean)"
          />
          <div class="form-hint">可用步骤: source, parser, ai, media, dispatch</div>
        </div>
        <div class="form-group">
          <label class="form-label">可选步骤 (跳过不报错)</label>
          <input
            class="form-input mono"
            :value="form.workflow.optional_steps?.join(', ')"
            @input="form.workflow.optional_steps = $event.target.value.split(',').map(s => s.trim()).filter(Boolean)"
          />
        </div>
        <div class="form-group">
          <label class="form-label">容错步骤 (失败继续)</label>
          <input
            class="form-input mono"
            :value="form.workflow.continue_on_error?.join(', ')"
            @input="form.workflow.continue_on_error = $event.target.value.split(',').map(s => s.trim()).filter(Boolean)"
          />
        </div>
        <div class="form-group">
          <label class="form-label">最大并发数</label>
          <input
            class="form-input"
            type="number"
            v-model.number="form.workflow.max_concurrency"
            min="1"
            max="20"
          />
        </div>
        <div class="form-group">
          <label class="form-label">默认重试次数</label>
          <input
            class="form-input"
            type="number"
            v-model.number="retries"
            min="0"
            max="10"
          />
        </div>
      </div>

      <!-- Runtime Settings -->
      <div class="card">
        <div class="card-header">
          <span class="card-title">⏰ 运行时 / 调度</span>
        </div>
        <div class="form-group">
          <label class="form-label">启用计划执行</label>
          <label class="toggle">
            <input type="checkbox" v-model="form.runtime.scheduler_enabled" />
            <span class="toggle-slider"></span>
          </label>
          <div class="form-hint">开启后，服务会按 Cron 配置自动调度 workflow。</div>
        </div>
        <div class="form-group">
          <label class="form-label">定时 Cron 表达式</label>
          <input
            class="form-input mono"
            v-model="form.runtime.schedule_cron"
            placeholder="0 */6 * * *"
          />
          <div class="form-hint">例如: 0 */6 * * * (每6小时执行一次)</div>
          <div class="form-hint">当前实现支持 `*`、`*/N`、单值、逗号列表和范围。</div>
        </div>
        <div class="form-group">
          <label class="form-label">时区</label>
          <input
            class="form-input"
            v-model="form.runtime.timezone"
            placeholder="Asia/Shanghai"
          />
          <div class="form-hint">建议使用 `UTC` 或 `Asia/Shanghai`。</div>
        </div>
      </div>

      <!-- Soul / AI Prompt -->
      <div class="card">
        <div class="card-header">
          <span class="card-title">🧠 AI 人格</span>
        </div>
        <div class="form-group">
          <label class="form-label">Admin Token</label>
          <input
            class="form-input mono"
            v-model="adminToken"
            type="password"
            placeholder="留空表示不保存本地 token"
          />
          <div class="form-hint">
            当服务端配置了 OMNIFLOW_ADMIN_TOKEN 时，配置保存、触发运行和人格编辑需要此 token。
          </div>
        </div>
        <div class="form-group">
          <label class="form-label">System Prompt (soul.md)</label>
          <textarea
            class="form-textarea"
            v-model="soulContent"
            rows="8"
            placeholder="加载中..."
          ></textarea>
          <div class="form-hint">
            定义 AI 模块的行为准则和输出格式约束
          </div>
        </div>
      </div>
    </div>

    <!-- Save Button -->
    <div class="mt-24 flex items-center gap-16">
      <button class="btn btn-primary" @click="saveConfig">
        💾 保存全局配置
      </button>
      <button class="btn btn-secondary" @click="resetConfig">
        ↩️ 重置
      </button>
      <span class="text-sm text-muted" v-if="msg">{{ msg }}</span>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { api, getAdminToken, setAdminToken } from '../api/client.js'

const form = ref({
  global: { project_name: 'Omni-InfoFlow', log_level: 'INFO' },
  workflow: {
    steps: ['source', 'parser', 'ai', 'media', 'dispatch'],
    optional_steps: ['ai', 'media'],
    continue_on_error: ['media'],
    max_concurrency: 3,
    retry_policy: { default_retries: 2 },
  },
  runtime: { scheduler_enabled: false, schedule_cron: '0 */6 * * *', timezone: 'Asia/Shanghai' },
})

const soulContent = ref('')
const adminToken = ref(getAdminToken())
const msg = ref('')

const retries = computed({
  get: () => form.value.workflow.retry_policy?.default_retries ?? 2,
  set: (v) => {
    if (!form.value.workflow.retry_policy) form.value.workflow.retry_policy = {}
    form.value.workflow.retry_policy.default_retries = v
  },
})

async function loadConfig() {
  try {
    const cfg = await api.getConfig()
    form.value.global = cfg.global || form.value.global
    form.value.workflow = cfg.workflow || form.value.workflow
    form.value.runtime = {
      ...form.value.runtime,
      ...(cfg.runtime || {}),
    }
  } catch (e) {
    msg.value = e.status === 401 ? '⚠️ 缺少或无效 Admin Token' : '⚠️ 加载失败: ' + e.message
  }

  try {
    const prompt = await api.getSoulPrompt()
    soulContent.value = prompt.content || ''
  } catch (e) {
    if (e.status === 401) {
      soulContent.value = ''
    }
  }
}

async function saveConfig() {
  setAdminToken(adminToken.value)
  adminToken.value = getAdminToken()

  try {
    await Promise.all([
      api.patchConfig({
        global: form.value.global,
        workflow: form.value.workflow,
        runtime: form.value.runtime,
      }),
      api.saveSoulPrompt(soulContent.value),
    ])
    msg.value = '✅ 配置已保存，调度状态已刷新'
    setTimeout(() => msg.value = '', 3000)
  } catch (e) {
    msg.value = e.status === 401 ? '❌ 缺少或无效 Admin Token' : '❌ 保存失败: ' + e.message
  }
}

async function resetConfig() {
  await loadConfig()
  msg.value = '↩️ 已重置为服务端配置'
  setTimeout(() => msg.value = '', 3000)
}

onMounted(loadConfig)
</script>
