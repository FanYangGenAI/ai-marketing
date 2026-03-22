<template>
  <!-- Already submitted -->
  <div v-if="existingFeedback" class="bg-white rounded-xl shadow-sm border border-gray-200">
    <div class="px-5 py-4 border-b border-gray-100">
      <h3 class="font-semibold text-gray-800">用户反馈</h3>
    </div>
    <div class="p-5">
      <div
        class="flex items-center gap-2 text-sm font-medium"
        :class="existingFeedback === 'accept' ? 'text-green-700' : 'text-red-700'"
      >
        <span>{{ existingFeedback === 'accept' ? '✅ 已接受' : '❌ 已拒绝' }}</span>
      </div>
    </div>
  </div>

  <!-- Feedback form -->
  <div v-else-if="auditPassed !== null" class="bg-white rounded-xl shadow-sm border border-gray-200">
    <div class="px-5 py-4 border-b border-gray-100">
      <h3 class="font-semibold text-gray-800">用户反馈</h3>
    </div>
    <div class="p-5 space-y-4">
      <p class="text-sm text-gray-600">请对今日生成的素材包作出反馈，以帮助 AI 持续优化。</p>

      <!-- Action toggle -->
      <div class="flex gap-3">
        <button
          @click="action = 'accept'"
          :class="action === 'accept'
            ? 'bg-green-600 text-white border-green-600'
            : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50'"
          class="flex-1 px-4 py-2 text-sm font-medium rounded-lg border transition-colors"
          :disabled="submitting"
        >✅ 接受</button>
        <button
          @click="action = 'reject'"
          :class="action === 'reject'
            ? 'bg-red-600 text-white border-red-600'
            : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50'"
          class="flex-1 px-4 py-2 text-sm font-medium rounded-lg border transition-colors"
          :disabled="submitting"
        >❌ 拒绝</button>
      </div>

      <!-- Rejection reason -->
      <div v-if="action === 'reject'">
        <label class="block text-sm font-medium text-gray-700 mb-1">
          拒绝原因 <span class="text-red-500">*</span>
        </label>
        <textarea
          v-model="reason"
          rows="3"
          placeholder="请说明拒绝的具体原因，AI 下次会参考此反馈..."
          class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-red-400 resize-none"
          :disabled="submitting"
        />
      </div>

      <!-- Error -->
      <div v-if="error" class="bg-red-50 border border-red-200 rounded-lg px-3 py-2 text-sm text-red-700">
        {{ error }}
      </div>

      <!-- Submit -->
      <button
        @click="submit"
        :disabled="!action || (action === 'reject' && !reason.trim()) || submitting"
        class="w-full px-4 py-2.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-medium rounded-lg transition-colors"
      >
        <span v-if="submitting">提交中...</span>
        <span v-else>提交反馈</span>
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { submitFeedback } from '../api/index.js'

const props = defineProps({
  product: { type: String, required: true },
  date: { type: String, required: true },
  auditPassed: { type: Boolean, default: null },
  existingFeedback: { type: String, default: null }, // "accept" | "reject" | null
})

const emit = defineEmits(['submitted'])

const action = ref(null)
const reason = ref('')
const submitting = ref(false)
const error = ref(null)

async function submit() {
  if (!action.value) return
  if (action.value === 'reject' && !reason.value.trim()) return
  submitting.value = true
  error.value = null
  try {
    await submitFeedback(props.product, props.date, action.value, reason.value.trim())
    emit('submitted', action.value)
  } catch (e) {
    error.value = e.message || '提交失败，请重试'
  } finally {
    submitting.value = false
  }
}
</script>
