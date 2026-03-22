<template>
  <!-- Backdrop -->
  <div
    class="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
    @click.self="$emit('close')"
  >
    <div class="bg-white text-gray-900 rounded-2xl shadow-xl w-full max-w-lg mx-4 overflow-hidden">
      <!-- Header -->
      <div class="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
        <h2 class="text-lg font-bold text-gray-900">新建产品项目</h2>
        <button
          @click="$emit('close')"
          class="text-gray-400 hover:text-gray-600 transition-colors text-xl leading-none"
        >✕</button>
      </div>

      <!-- Form -->
      <div class="px-6 py-5 space-y-4">
        <!-- 产品名称 -->
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">产品名称 <span class="text-red-500">*</span></label>
          <input
            v-model="name"
            type="text"
            placeholder="例如：原语、MyApp、TravelBot"
            class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm text-gray-900 placeholder:text-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
            :disabled="submitting"
          />
        </div>

        <!-- 产品需求描述 -->
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">
            产品需求描述（user_brief）
            <span class="text-gray-400 font-normal ml-1">— 每次流水线都会参考</span>
          </label>
          <textarea
            v-model="userBrief"
            rows="4"
            placeholder="描述你的产品：目标用户、核心功能、品牌调性、营销目标等..."
            class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm text-gray-900 placeholder:text-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
            :disabled="submitting"
          />
          <p class="text-xs text-gray-400 mt-1">可选，但填写后 AI 的策略和文案质量会更贴合产品实际</p>
        </div>

        <!-- PRD upload (optional) -->
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">产品 PRD（可选）</label>
          <p class="text-xs text-gray-500 mb-2">创建后将写入配置中的 prd_path，流水线可自动加载。支持 .md / .txt / .pdf / .doc / .docx。</p>
          <div class="flex flex-wrap items-center gap-2">
            <label class="inline-flex items-center px-3 py-2 bg-gray-100 hover:bg-gray-200 rounded-lg text-sm text-gray-800 cursor-pointer">
              选择文件
              <input
                type="file"
                class="hidden"
                accept=".md,.txt,.pdf,.doc,.docx"
                :disabled="submitting"
                @change="onPrdChange"
              />
            </label>
            <span v-if="prdLabel" class="text-sm text-gray-600 truncate max-w-[220px]">{{ prdLabel }}</span>
            <span v-else class="text-sm text-gray-400">未选择</span>
          </div>
        </div>

        <!-- Reference files (optional) -->
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">附件文件（可选，可多选）</label>
          <p class="text-xs text-gray-500 mb-2">图片、截图、视频、文档等保存到 docs/materials/；当前不会自动参与流水线。可在「产品设置」中补传。</p>
          <label class="inline-flex items-center px-3 py-2 bg-gray-100 hover:bg-gray-200 rounded-lg text-sm text-gray-800 cursor-pointer">
            选择文件
            <input
              type="file"
              class="hidden"
              multiple
              :disabled="submitting"
              @change="onAttachmentsChange"
            />
          </label>
          <span v-if="attachmentCount" class="text-sm text-gray-600 ml-2">已选 {{ attachmentCount }} 个文件</span>
        </div>

        <!-- 错误提示 -->
        <div v-if="error" class="bg-red-50 border border-red-200 rounded-lg px-3 py-2 text-sm text-red-700">
          {{ error }}
        </div>
      </div>

      <!-- Footer -->
      <div class="px-6 py-4 border-t border-gray-200 flex justify-end gap-3">
        <button
          @click="$emit('close')"
          class="px-4 py-2 text-sm text-gray-600 hover:text-gray-800 transition-colors"
          :disabled="submitting"
        >取消</button>
        <button
          @click="submit"
          class="px-5 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium rounded-lg transition-colors disabled:opacity-50"
          :disabled="!name.trim() || submitting"
        >
          <span v-if="submitting">创建中...</span>
          <span v-else>创建项目</span>
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import {
  createProduct,
  uploadProductAttachments,
  uploadProductPrd,
} from '../api/index.js'

const emit = defineEmits(['close', 'created'])

const name = ref('')
const userBrief = ref('')
const submitting = ref(false)
const error = ref(null)

const prdFile = ref(null)
const prdLabel = ref('')
const attachmentList = ref([])

const attachmentCount = computed(() => attachmentList.value.length)

function onPrdChange(e) {
  const f = e.target.files?.[0]
  prdFile.value = f || null
  prdLabel.value = f ? f.name : ''
  e.target.value = ''
}

function onAttachmentsChange(e) {
  attachmentList.value = e.target.files ? Array.from(e.target.files) : []
  e.target.value = ''
}

async function submit() {
  if (!name.value.trim()) return
  submitting.value = true
  error.value = null
  const productName = name.value.trim()
  try {
    await createProduct(productName, userBrief.value.trim())
  } catch (e) {
    error.value = e.message || '创建失败，请重试'
    submitting.value = false
    return
  }

  emit('created', productName)

  try {
    if (prdFile.value) {
      await uploadProductPrd(productName, prdFile.value)
    }
    if (attachmentList.value.length) {
      await uploadProductAttachments(productName, attachmentList.value)
    }
  } catch (e) {
    error.value =
      `产品已创建，但文件上传失败：${e.message || '未知错误'}。请在侧栏进入「产品设置」重新上传。`
    submitting.value = false
    return
  }

  prdFile.value = null
  prdLabel.value = ''
  attachmentList.value = []
  submitting.value = false
  emit('close')
}
</script>
