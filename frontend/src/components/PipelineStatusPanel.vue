<template>
  <!-- 右下角悬浮状态面板 -->
  <div
    v-if="visible"
    class="fixed bottom-5 right-5 z-40 bg-white rounded-xl shadow-lg border border-gray-200 overflow-hidden transition-all"
    :class="collapsed ? 'w-56' : 'w-72'"
  >
    <!-- Header bar -->
    <div
      class="flex items-center gap-2 px-3 py-2.5 cursor-pointer select-none"
      :class="running ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-700'"
      @click="collapsed = !collapsed"
    >
      <span class="text-sm">{{ running ? '🔄' : (lastSuccess ? '✅' : '⬜') }}</span>
      <span class="text-xs font-medium flex-1">
        {{ running ? `流水线运行中 · ${currentStageLabel}` : (lastSuccess === true ? '流水线已完成' : (lastSuccess === false ? '流水线未通过' : '流水线状态')) }}
      </span>
      <svg
        class="w-3.5 h-3.5 flex-shrink-0 transition-transform"
        :class="collapsed ? 'rotate-180' : ''"
        fill="none" stroke="currentColor" viewBox="0 0 24 24"
      >
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 15l7-7 7 7"/>
      </svg>
    </div>

    <!-- Stages list -->
    <div v-if="!collapsed" class="px-3 py-2 space-y-1">
      <div
        v-for="stage in stages"
        :key="stage.key"
        class="flex items-center gap-2 py-1"
      >
        <span class="text-sm w-4 text-center flex-shrink-0">{{ stage.icon }}</span>
        <span class="text-xs text-gray-700 flex-1">{{ stage.label }}</span>
        <span v-if="stage.time" class="text-xs text-gray-400">{{ stage.time }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onUnmounted } from 'vue'
import { getRunStatus } from '../api/index.js'

const props = defineProps({
  product: { type: String, default: '' },
})

const emit = defineEmits(['completed'])

const statusData = ref(null)
const collapsed = ref(false)
let pollTimer = null

const STAGE_LABELS = {
  strategist: '策略 (Strategist)',
  planner: '规划 (Planner)',
  scriptwriter: '文案 (Scriptwriter)',
  director: '编排 (Director)',
  creator: '组装 (Creator)',
  audit: '审核 (Audit)',
}

const running = computed(() => statusData.value?.running === true)
const visible = computed(() => !!statusData.value)

const currentStageLabel = computed(() => {
  const s = statusData.value?.current_stage
  return s ? STAGE_LABELS[s] || s : '...'
})

const lastSuccess = computed(() => {
  const stages = statusData.value?.stages || {}
  if (!stages.audit) return null
  if (!stages.audit.done) return null
  return stages.audit.success === true
})

const stages = computed(() => {
  const s = statusData.value?.stages || {}
  return ['strategist', 'planner', 'scriptwriter', 'director', 'creator', 'audit'].map(key => {
    const st = s[key] || {}
    let icon = '⏳'
    if (st.done) icon = st.success ? '✅' : '❌'
    else if (statusData.value?.current_stage === key) icon = '🔄'
    return {
      key,
      label: STAGE_LABELS[key] || key,
      icon,
      time: st.timestamp ? st.timestamp.slice(11, 19) : null,
    }
  })
})

async function poll() {
  if (!props.product) return
  try {
    statusData.value = await getRunStatus(props.product)
    if (!running.value && statusData.value) {
      // 完成后停止轮询，通知父组件
      stopPolling()
      emit('completed')
      // 5 秒后自动折叠
      setTimeout(() => { collapsed.value = true }, 5000)
    }
  } catch {
    // ignore
  }
}

function startPolling() {
  if (pollTimer) return
  pollTimer = setInterval(poll, 3000)
  poll() // 立即执行一次
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

// 当 product 变化时重新开始轮询
watch(() => props.product, (p) => {
  if (p) {
    statusData.value = null
    startPolling()
  } else {
    stopPolling()
    statusData.value = null
  }
}, { immediate: true })

// 外部可调用
defineExpose({ startPolling, stopPolling })

onUnmounted(stopPolling)
</script>
