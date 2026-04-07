<template>
  <div class="bg-white rounded-xl shadow-sm border border-gray-200">
    <div class="px-5 py-4 border-b border-gray-100">
      <h3 class="font-semibold text-gray-800">运行流水线</h3>
    </div>
    <div class="p-5 space-y-4">
      <!-- today_note input -->
      <div>
        <label class="block text-sm font-medium text-gray-700 mb-1">
          今日特殊要求
          <span class="text-gray-400 font-normal ml-1">— 可选，优先于默认策略</span>
        </label>
        <textarea
          v-model="todayNote"
          rows="3"
          placeholder="例如：今天重点推「多语言支持」新功能，文案突出国际化场景..."
          class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
          :disabled="running || submitting"
        />
      </div>

      <!-- Error -->
      <div v-if="error" class="bg-red-50 border border-red-200 rounded-lg px-3 py-2 text-sm text-red-700">
        {{ error }}
      </div>

      <!-- Run button -->
      <button
        @click="startRun"
        :disabled="running || submitting"
        class="w-full px-4 py-2.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-medium rounded-lg transition-colors flex items-center justify-center gap-2"
      >
        <span v-if="running">🔄 流水线运行中...</span>
        <span v-else-if="submitting">启动中...</span>
        <span v-else>🚀 开始运行流水线</span>
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { runPipeline } from '../api/index.js'

const props = defineProps({
  product: { type: String, required: true },
  running: { type: Boolean, default: false },
})

const emit = defineEmits(['started'])

const todayNote = ref('')
const submitting = ref(false)
const error = ref(null)

async function startRun() {
  if (!props.product || props.running || submitting.value) return
  submitting.value = true
  error.value = null
  try {
    await runPipeline(props.product, todayNote.value.trim())
    emit('started')
    todayNote.value = ''
  } catch (e) {
    error.value = e.message || '启动失败，请重试'
  } finally {
    submitting.value = false
  }
}
</script>
