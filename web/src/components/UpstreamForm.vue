<script setup lang="ts">
import { ref, watch } from 'vue'
import type { UpstreamConfig } from '../api'

const props = defineProps<{
  upstream: UpstreamConfig
  cooldownSeconds: number
  probeEnabled: boolean
  probeIntervalSeconds: number
}>()

const emit = defineEmits<{
  (e: 'update:upstream', v: UpstreamConfig): void
  (e: 'update:cooldownSeconds', v: number): void
  (e: 'update:probeEnabled', v: boolean): void
  (e: 'update:probeIntervalSeconds', v: number): void
  (e: 'probe'): void
}>()

const localUpstream = ref<UpstreamConfig>({ ...props.upstream })
const localCooldown = ref<number>(props.cooldownSeconds)
const localProbeEnabled = ref<boolean>(props.probeEnabled)
const localProbeInterval = ref<number>(props.probeIntervalSeconds)
const editingKey = ref(false)
const originalKey = ref(props.upstream.api_key)

watch(
  () => props.upstream,
  (v) => {
    localUpstream.value = { ...v }
    originalKey.value = v.api_key
    editingKey.value = false
  },
  { deep: true }
)

watch(
  () => props.cooldownSeconds,
  (v) => {
    localCooldown.value = v
  }
)

watch(
  () => props.probeEnabled,
  (v) => {
    localProbeEnabled.value = v
  }
)

watch(
  () => props.probeIntervalSeconds,
  (v) => {
    localProbeInterval.value = v
  }
)

function emitUpstream() {
  emit('update:upstream', { ...localUpstream.value })
}

function emitCooldown() {
  emit('update:cooldownSeconds', Number(localCooldown.value) || 30)
}

function emitProbeEnabled() {
  emit('update:probeEnabled', Boolean(localProbeEnabled.value))
}

function emitProbeInterval() {
  const v = Number(localProbeInterval.value)
  emit('update:probeIntervalSeconds', v >= 10 ? v : 10)
}

function toggleEditKey() {
  if (editingKey.value) {
    editingKey.value = false
    localUpstream.value.api_key = originalKey.value
    emitUpstream()
  } else {
    editingKey.value = true
    localUpstream.value.api_key = ''
  }
}
</script>

<template>
  <div class="card">
    <h2>上游配置</h2>
    <div class="row">
      <label>base_url</label>
      <input
        type="text"
        v-model="localUpstream.base_url"
        placeholder="https://newapi.example.com"
        @change="emitUpstream"
      />
    </div>
    <div class="row">
      <label>api_key</label>
      <input
        v-if="editingKey"
        type="text"
        v-model="localUpstream.api_key"
        placeholder="sk-..."
        @change="emitUpstream"
      />
      <input v-else type="text" :value="localUpstream.api_key" disabled />
      <button @click="toggleEditKey">{{ editingKey ? '取消' : '编辑' }}</button>
    </div>
    <div class="row">
      <label>冷却秒数</label>
      <input
        type="number"
        v-model.number="localCooldown"
        min="0"
        @change="emitCooldown"
        style="max-width: 120px"
      />
      <label style="min-width: 80px">请求超时</label>
      <input
        type="number"
        v-model.number="localUpstream.request_timeout"
        min="1"
        step="1"
        @change="emitUpstream"
        style="max-width: 120px"
      />
      <label style="min-width: 100px">首chunk超时</label>
      <input
        type="number"
        v-model.number="localUpstream.first_chunk_timeout"
        min="1"
        step="1"
        @change="emitUpstream"
        style="max-width: 120px"
      />
    </div>
    <div class="row">
      <label>主动探测</label>
      <input
        type="checkbox"
        v-model="localProbeEnabled"
        @change="emitProbeEnabled"
      />
      <label style="min-width: 100px">探测间隔(秒)</label>
      <input
        type="number"
        v-model.number="localProbeInterval"
        min="10"
        step="10"
        :disabled="!localProbeEnabled"
        @change="emitProbeInterval"
        style="max-width: 120px"
      />
    </div>
    <div class="row">
      <button @click="emit('probe')">从上游拉取模型列表</button>
    </div>
    <div class="hint">
      冷却：模型出错后多少秒内不再尝试。请求超时：单次上游请求最长等待。首chunk超时：流式响应首个 token 的最长等待。主动探测：按间隔对已启用模型发最小请求，失败即进入冷却。
    </div>
  </div>
</template>
