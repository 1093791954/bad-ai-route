<script setup lang="ts">
import { ref } from 'vue'
import draggable from 'vuedraggable'
import type { ModelEntry, ModelHealth } from '../api'

const props = defineProps<{
  models: ModelEntry[]
  health: Record<string, ModelHealth>
}>()

const emit = defineEmits<{
  (e: 'update:models', v: ModelEntry[]): void
}>()

const newModelName = ref('')

function onReorder(list: ModelEntry[]) {
  emit('update:models', [...list])
}

function toggleEnabled(idx: number) {
  const next = props.models.map((m, i) =>
    i === idx ? { ...m, enabled: !m.enabled } : m
  )
  emit('update:models', next)
}

function removeModel(idx: number) {
  const next = props.models.filter((_, i) => i !== idx)
  emit('update:models', next)
}

function addModel() {
  const name = newModelName.value.trim()
  if (!name) return
  if (props.models.some((m) => m.name === name)) {
    newModelName.value = ''
    return
  }
  emit('update:models', [...props.models, { name, enabled: true }])
  newModelName.value = ''
}

function statusOf(name: string): { text: string; cls: string } {
  const h = props.health[name]
  if (!h) return { text: '—', cls: 'status-idle' }
  if (h.available) return { text: '可用', cls: 'status-ok' }
  return {
    text: `冷却 ${Math.ceil(h.cooldown_remaining)}s`,
    cls: 'status-cooldown',
  }
}
</script>

<template>
  <div class="card">
    <h2>模型顺序（拖拽排序，勾选启用）</h2>
    <div v-if="models.length === 0" class="empty">
      还没有模型。点上方"从上游拉取模型列表"，或在下方手动添加。
    </div>
    <draggable
      v-else
      :model-value="models"
      @update:model-value="onReorder"
      tag="ul"
      class="model-list"
      item-key="name"
      handle=".drag-handle"
      ghost-class="ghost"
      animation="150"
    >
      <template #item="{ element, index }">
        <li class="model-item">
          <span class="drag-handle">≡</span>
          <input
            type="checkbox"
            :checked="element.enabled"
            @change="toggleEnabled(index)"
          />
          <span class="model-name">{{ element.name }}</span>
          <span class="status-badge" :class="statusOf(element.name).cls">
            {{ statusOf(element.name).text }}
          </span>
          <button @click="removeModel(index)" title="移除">✕</button>
        </li>
      </template>
    </draggable>

    <div class="manual-add">
      <input
        type="text"
        v-model="newModelName"
        placeholder="手动添加模型名，如 claude-opus-4-7"
        @keydown.enter="addModel"
      />
      <button @click="addModel">添加</button>
    </div>
  </div>
</template>
