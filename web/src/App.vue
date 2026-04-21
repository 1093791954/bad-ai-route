<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import UpstreamForm from './components/UpstreamForm.vue'
import ModelRankList from './components/ModelRankList.vue'
import { api } from './api'
import type { Settings, ModelEntry, UpstreamConfig, ModelHealth } from './api'

const settings = ref<Settings>({
  listen_host: '127.0.0.1',
  listen_port: 18624,
  cooldown_seconds: 30,
  probe_enabled: true,
  probe_interval_seconds: 300,
  upstream: {
    base_url: '',
    api_key: '',
    request_timeout: 60,
    first_chunk_timeout: 20,
  },
  models: [],
})

const health = ref<Record<string, ModelHealth>>({})
const loading = ref(false)
const saving = ref(false)
const probing = ref(false)
const toast = ref<{ msg: string; type: 'success' | 'error' | 'info' } | null>(null)
let healthTimer: number | null = null
let toastTimer: number | null = null

function showToast(msg: string, type: 'success' | 'error' | 'info' = 'info') {
  toast.value = { msg, type }
  if (toastTimer) window.clearTimeout(toastTimer)
  toastTimer = window.setTimeout(() => {
    toast.value = null
  }, 2800)
}

async function loadConfig() {
  loading.value = true
  try {
    const data = await api.getConfig()
    settings.value = data
  } catch (e: any) {
    showToast(`加载配置失败: ${e.message}`, 'error')
  } finally {
    loading.value = false
  }
}

async function refreshHealth() {
  try {
    const data = await api.getHealth()
    health.value = data.models
  } catch {
    // silent
  }
}

async function saveConfig() {
  saving.value = true
  try {
    await api.updateConfig(settings.value)
    showToast('配置已保存', 'success')
    // Reload to get fresh masked key
    await loadConfig()
  } catch (e: any) {
    showToast(`保存失败: ${e.message}`, 'error')
  } finally {
    saving.value = false
  }
}

async function probeModels() {
  // Save current config first so probe uses the latest base_url/key
  try {
    await api.updateConfig(settings.value)
  } catch (e: any) {
    showToast(`保存失败: ${e.message}`, 'error')
    return
  }

  probing.value = true
  try {
    const resp = await api.probeModels()
    if (resp.status === 'error' || !resp.models || resp.models.length === 0) {
      showToast(resp.message || '未能获取模型列表', 'error')
      return
    }

    // Merge: keep existing entries (and their order/enabled), append new ones
    const existing = new Set(settings.value.models.map((m) => m.name))
    const merged: ModelEntry[] = [...settings.value.models]
    for (const name of resp.models) {
      if (!existing.has(name)) {
        merged.push({ name, enabled: false })
      }
    }
    settings.value.models = merged
    await loadConfig() // reload masked key
    settings.value.models = merged // keep merged result after reload
    showToast(`拉取到 ${resp.models.length} 个模型`, 'success')
  } catch (e: any) {
    showToast(`拉取失败: ${e.message}`, 'error')
  } finally {
    probing.value = false
  }
}

async function resetCooldowns() {
  try {
    await api.resetHealth()
    await refreshHealth()
    showToast('已清除所有冷却', 'success')
  } catch (e: any) {
    showToast(`清除失败: ${e.message}`, 'error')
  }
}

function onUpdateUpstream(v: UpstreamConfig) {
  settings.value.upstream = v
}

function onUpdateCooldown(v: number) {
  settings.value.cooldown_seconds = v
}

function onUpdateProbeEnabled(v: boolean) {
  settings.value.probe_enabled = v
}

function onUpdateProbeInterval(v: number) {
  settings.value.probe_interval_seconds = v
}

function onUpdateModels(v: ModelEntry[]) {
  settings.value.models = v
}

async function probeAllNow() {
  try {
    await api.probeHealth()
    await refreshHealth()
    showToast('已触发全量探测', 'success')
  } catch (e: any) {
    showToast(`探测失败: ${e.message}`, 'error')
  }
}

async function probeOneModel(name: string) {
  try {
    await api.probeModelHealth(name)
    await refreshHealth()
    showToast(`已探测 ${name}`, 'success')
  } catch (e: any) {
    showToast(`探测失败: ${e.message}`, 'error')
  }
}

onMounted(async () => {
  await loadConfig()
  await refreshHealth()
  healthTimer = window.setInterval(refreshHealth, 3000)
})

onUnmounted(() => {
  if (healthTimer) window.clearInterval(healthTimer)
  if (toastTimer) window.clearTimeout(toastTimer)
})
</script>

<template>
  <h1>AI-Route 配置</h1>

  <UpstreamForm
    :upstream="settings.upstream"
    :cooldown-seconds="settings.cooldown_seconds"
    :probe-enabled="settings.probe_enabled"
    :probe-interval-seconds="settings.probe_interval_seconds"
    @update:upstream="onUpdateUpstream"
    @update:cooldown-seconds="onUpdateCooldown"
    @update:probe-enabled="onUpdateProbeEnabled"
    @update:probe-interval-seconds="onUpdateProbeInterval"
    @probe="probeModels"
  />

  <ModelRankList
    :models="settings.models"
    :health="health"
    @update:models="onUpdateModels"
    @probe-one="probeOneModel"
  />

  <div class="card">
    <div class="actions">
      <button class="primary" @click="saveConfig" :disabled="saving">
        {{ saving ? '保存中...' : '保存配置' }}
      </button>
      <button @click="resetCooldowns">手动清除冷却</button>
      <button @click="probeAllNow">立即全量探测</button>
      <button @click="probeModels" :disabled="probing">
        {{ probing ? '拉取中...' : '拉取模型列表' }}
      </button>
    </div>
  </div>

  <div class="card">
    <h2>反代地址</h2>
    <div class="endpoints">
      <div>Base: http://{{ settings.listen_host }}:{{ settings.listen_port }}</div>
      <div>Anthropic: /v1/messages</div>
      <div>OpenAI:    /v1/chat/completions</div>
    </div>
    <div class="hint" style="margin-top: 8px">
      在 CC switch 中把 ANTHROPIC_BASE_URL 指向上面的 Base 地址，API Key 随便填即可。
    </div>
  </div>

  <div v-if="loading" class="hint">加载中...</div>

  <div v-if="toast" class="toast" :class="toast.type">{{ toast.msg }}</div>
</template>
