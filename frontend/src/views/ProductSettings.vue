<template>
  <div class="min-h-screen bg-gray-50">
    <div class="bg-white border-b border-gray-200 px-6 py-4">
      <div class="max-w-3xl mx-auto flex items-center gap-3">
        <h2 class="text-lg font-bold text-gray-900">{{ product }} — 产品设置</h2>
        <span class="text-sm text-gray-500">PRD、附件文件与需求描述</span>
      </div>
    </div>

    <div class="max-w-3xl mx-auto px-6 py-6 space-y-6">
      <div v-if="loading" class="text-center py-12 text-gray-500">加载中...</div>
      <div v-else-if="loadError" class="bg-red-50 border border-red-200 rounded-xl p-4 text-red-700 text-sm">
        {{ loadError }}
      </div>

      <template v-else>
        <!-- user_brief -->
        <div class="bg-white rounded-xl shadow-sm border border-gray-200 p-5">
          <h3 class="font-semibold text-gray-800 mb-1">产品需求描述（user_brief）</h3>
          <p class="text-xs text-gray-500 mb-3">每次流水线都会参考；可与 PRD 互补。</p>
          <textarea
            v-model="userBriefDraft"
            rows="5"
            class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm text-gray-900 placeholder:text-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
            placeholder="目标用户、核心功能、品牌调性、营销目标等..."
          />
          <div class="mt-3 flex justify-end">
            <button
              type="button"
              :disabled="briefSaving"
              class="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-sm font-medium rounded-lg"
              @click="saveBrief"
            >
              {{ briefSaving ? '保存中…' : '保存描述' }}
            </button>
          </div>
          <p v-if="briefMessage" class="text-xs mt-2" :class="briefError ? 'text-red-600' : 'text-green-600'">
            {{ briefMessage }}
          </p>
        </div>

        <!-- PRD -->
        <div class="bg-white rounded-xl shadow-sm border border-gray-200 p-5">
          <h3 class="font-semibold text-gray-800 mb-1">产品 PRD</h3>
          <p class="text-xs text-gray-500 mb-3">
            上传后写入 <code class="text-gray-700 bg-gray-100 px-1 rounded">product_config.json</code> 的
            <code class="text-gray-700 bg-gray-100 px-1 rounded">prd_path</code>，流水线会自动加载。
          </p>
          <p v-if="documents?.prd_path" class="text-sm text-gray-700 mb-2 break-all">
            当前：<span class="font-mono text-xs">{{ documents.prd_path }}</span>
          </p>
          <p v-else class="text-sm text-amber-700 mb-2">尚未设置 PRD 文件。</p>
          <div class="flex flex-wrap items-center gap-3">
            <label class="inline-flex items-center gap-2 px-4 py-2 bg-gray-100 hover:bg-gray-200 rounded-lg text-sm text-gray-800 cursor-pointer">
              <span>选择 PRD 文件</span>
              <input type="file" class="hidden" accept=".md,.txt,.pdf,.doc,.docx" @change="onPrdPick" />
            </label>
            <span v-if="prdPickName" class="text-sm text-gray-600">{{ prdPickName }}</span>
            <button
              type="button"
              :disabled="!prdFile || prdUploading"
              class="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-sm font-medium rounded-lg"
              @click="uploadPrd"
            >
              {{ prdUploading ? '上传中…' : '上传并设为 PRD' }}
            </button>
          </div>
          <p v-if="prdMessage" class="text-xs mt-2" :class="prdError ? 'text-red-600' : 'text-green-600'">
            {{ prdMessage }}
          </p>
        </div>

        <!-- Cold-start images → manifest + Asset Library -->
        <div class="bg-white rounded-xl shadow-sm border border-blue-100 p-5 ring-1 ring-blue-50">
          <h3 class="font-semibold text-gray-800 mb-1">冷启动图片（入库 + 可理解）</h3>
          <p class="text-xs text-gray-500 mb-3">
            上传 <strong class="text-gray-700">PNG / JPG / WebP</strong> 至素材库并登记清单；可一键生成
            <code class="text-gray-700 bg-gray-100 px-1 rounded">product_profile.json</code> 供 Strategist 使用。
            <span class="text-amber-700 font-medium">不支持视频、GIF 动图上传。</span>
          </p>
          <div class="flex flex-wrap items-center gap-3 mb-3">
            <label class="text-sm text-gray-600">分类标签</label>
            <select
              v-model="coldTag"
              class="text-sm border border-gray-300 rounded-lg px-2 py-1.5 text-gray-800"
            >
              <option value="brand">brand（Logo / 品牌）</option>
              <option value="product_ui">product_ui（产品界面）</option>
              <option value="marketing_ref">marketing_ref（营销参考图）</option>
            </select>
          </div>
          <label class="inline-flex items-center gap-2 px-4 py-2 bg-gray-100 hover:bg-gray-200 rounded-lg text-sm text-gray-800 cursor-pointer mb-3">
            <span>选择图片（可多选）</span>
            <input
              type="file"
              class="hidden"
              accept=".png,.jpg,.jpeg,.webp,image/png,image/jpeg,image/webp"
              multiple
              @change="onColdPick"
            />
          </label>
          <div v-if="coldNames.length" class="text-xs text-gray-600 mb-2">{{ coldNames.join(', ') }}</div>
          <div class="flex flex-wrap gap-2">
            <button
              type="button"
              :disabled="!coldFiles.length || coldUploading"
              class="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-sm font-medium rounded-lg"
              @click="uploadColdImages"
            >
              {{ coldUploading ? '上传中…' : '上传到素材库' }}
            </button>
            <button
              type="button"
              :disabled="coldUnderstandRunning || coldUnderstandStarting"
              class="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white text-sm font-medium rounded-lg"
              @click="runUnderstand"
            >
              {{ coldUnderstandStarting ? '启动中…' : '运行产品理解' }}
            </button>
          </div>
          <p v-if="coldMsg" class="text-xs mt-2" :class="coldErr ? 'text-red-600' : 'text-green-600'">{{ coldMsg }}</p>
          <div class="mt-3 text-xs text-gray-600 space-y-1">
            <p>
              理解任务状态：
              <span class="font-mono">{{ coldStatus?.status || 'idle' }}</span>
              <span v-if="coldStatus?.process_running" class="text-blue-600 ml-1">（子进程运行中）</span>
            </p>
            <p v-if="coldStatus?.product_profile_exists" class="text-green-700">已生成 product_profile.json</p>
          </div>
        </div>

        <!-- Reference attachments -->
        <div class="bg-white rounded-xl shadow-sm border border-gray-200 p-5">
          <h3 class="font-semibold text-gray-800 mb-1">附件文件（可选）</h3>
          <p class="text-xs text-gray-500 mb-3">
            保存到 <code class="text-gray-700 bg-gray-100 px-1 rounded">docs/materials/</code>（任意文件归档）。
            若需进入流水线素材库与产品理解，请使用上方「冷启动图片」。
          </p>
          <label class="inline-flex items-center gap-2 px-4 py-2 bg-gray-100 hover:bg-gray-200 rounded-lg text-sm text-gray-800 cursor-pointer mb-3">
            <span>选择文件（可多选）</span>
            <input type="file" class="hidden" multiple @change="onAttachPick" />
          </label>
          <div v-if="attachNames.length" class="text-xs text-gray-600 mb-2">{{ attachNames.join(', ') }}</div>
          <button
            type="button"
            :disabled="!attachFiles.length || attachUploading"
            class="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-sm font-medium rounded-lg"
            @click="uploadAttachments"
          >
            {{ attachUploading ? '上传中…' : '上传附件文件' }}
          </button>
          <p v-if="attachMessage" class="text-xs mt-2" :class="attachError ? 'text-red-600' : 'text-green-600'">
            {{ attachMessage }}
          </p>

          <div v-if="materialFiles.length" class="mt-4 border-t border-gray-100 pt-4">
            <h4 class="text-sm font-medium text-gray-700 mb-2">已上传附件</h4>
            <ul class="text-sm text-gray-600 space-y-1 font-mono text-xs">
              <li v-for="f in materialFiles" :key="f.path">{{ f.name }} ({{ formatSize(f.size) }})</li>
            </ul>
          </div>
        </div>

        <!-- docs root files (excluding materials) -->
        <div v-if="docsOnlyFiles.length" class="bg-white rounded-xl shadow-sm border border-gray-200 p-5">
          <h3 class="font-semibold text-gray-800 mb-2">docs 目录下的文件</h3>
          <ul class="text-sm text-gray-600 space-y-1 font-mono text-xs">
            <li v-for="f in docsOnlyFiles" :key="f.path">{{ f.name }} ({{ formatSize(f.size) }})</li>
          </ul>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { computed, onUnmounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import {
  getColdStartStatus,
  getConfig,
  listProductDocuments,
  triggerColdStartUnderstand,
  updateConfig,
  uploadColdStartImages,
  uploadProductAttachments,
  uploadProductPrd,
} from '../api/index.js'

const route = useRoute()
const product = computed(() => decodeURIComponent(route.params.product || ''))

const loading = ref(true)
const loadError = ref(null)
const documents = ref(null)
const userBriefDraft = ref('')

const briefSaving = ref(false)
const briefMessage = ref('')
const briefError = ref(false)

const prdFile = ref(null)
const prdPickName = ref('')
const prdUploading = ref(false)
const prdMessage = ref('')
const prdError = ref(false)

const attachFiles = ref([])
const attachNames = ref([])
const attachUploading = ref(false)
const attachMessage = ref('')
const attachError = ref(false)

const coldTag = ref('product_ui')
const coldFiles = ref([])
const coldNames = ref([])
const coldUploading = ref(false)
const coldMsg = ref('')
const coldErr = ref(false)
const coldStatus = ref(null)
const coldUnderstandStarting = ref(false)
const coldUnderstandRunning = ref(false)
let coldPollTimer = null

const materialFiles = computed(() =>
  (documents.value?.files || []).filter((f) => f.category === 'materials')
)

const docsOnlyFiles = computed(() =>
  (documents.value?.files || []).filter((f) => f.category === 'docs')
)

function formatSize(n) {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / (1024 * 1024)).toFixed(1)} MB`
}

function onPrdPick(e) {
  const f = e.target.files?.[0]
  prdFile.value = f || null
  prdPickName.value = f ? f.name : ''
  prdMessage.value = ''
  e.target.value = ''
}

function onAttachPick(e) {
  const list = e.target.files ? Array.from(e.target.files) : []
  attachFiles.value = list
  attachNames.value = list.map((x) => x.name)
  attachMessage.value = ''
  e.target.value = ''
}

function onColdPick(e) {
  const list = e.target.files ? Array.from(e.target.files) : []
  coldFiles.value = list
  coldNames.value = list.map((x) => x.name)
  coldMsg.value = ''
  e.target.value = ''
}

async function refreshColdStatus() {
  try {
    coldStatus.value = await getColdStartStatus(product.value)
    coldUnderstandRunning.value =
      Boolean(coldStatus.value?.process_running) || coldStatus.value?.status === 'running'
    if (
      coldPollTimer &&
      !coldUnderstandRunning.value &&
      ['done', 'error', 'skipped'].includes(coldStatus.value?.status)
    ) {
      stopColdPoll()
    }
  } catch {
    coldStatus.value = null
  }
}

function startColdPoll() {
  if (coldPollTimer) clearInterval(coldPollTimer)
  coldPollTimer = setInterval(refreshColdStatus, 2000)
}

function stopColdPoll() {
  if (coldPollTimer) {
    clearInterval(coldPollTimer)
    coldPollTimer = null
  }
}

async function uploadColdImages() {
  if (!coldFiles.value.length) return
  coldUploading.value = true
  coldMsg.value = ''
  coldErr.value = false
  try {
    const res = await uploadColdStartImages(product.value, coldFiles.value, coldTag.value)
    coldMsg.value = `已入库 ${res.items?.length || 0} 张图片`
    coldFiles.value = []
    coldNames.value = []
    await refreshColdStatus()
  } catch (e) {
    coldErr.value = true
    coldMsg.value = e.message || '上传失败'
  } finally {
    coldUploading.value = false
  }
}

async function runUnderstand() {
  coldUnderstandStarting.value = true
  coldMsg.value = ''
  coldErr.value = false
  try {
    await triggerColdStartUnderstand(product.value)
    coldMsg.value = '理解任务已启动（后台运行，请稍后查看状态）'
    startColdPoll()
    await refreshColdStatus()
  } catch (e) {
    coldErr.value = true
    coldMsg.value = e.message || '启动失败'
  } finally {
    coldUnderstandStarting.value = false
  }
}

async function loadAll() {
  loading.value = true
  loadError.value = null
  try {
    const [docList, cfg] = await Promise.all([
      listProductDocuments(product.value),
      getConfig(product.value),
    ])
    documents.value = docList
    userBriefDraft.value = cfg.user_brief || ''
    await refreshColdStatus()
    if (coldUnderstandRunning.value) startColdPoll()
    else stopColdPoll()
  } catch (e) {
    loadError.value = e.message || '加载失败'
  } finally {
    loading.value = false
  }
}

async function saveBrief() {
  briefSaving.value = true
  briefMessage.value = ''
  briefError.value = false
  try {
    await updateConfig(product.value, { user_brief: userBriefDraft.value })
    briefMessage.value = '已保存'
  } catch (e) {
    briefError.value = true
    briefMessage.value = e.message || '保存失败'
  } finally {
    briefSaving.value = false
  }
}

async function uploadPrd() {
  if (!prdFile.value) return
  prdUploading.value = true
  prdMessage.value = ''
  prdError.value = false
  try {
    await uploadProductPrd(product.value, prdFile.value)
    prdMessage.value = 'PRD 已上传并写入配置'
    prdFile.value = null
    prdPickName.value = ''
    await loadAll()
  } catch (e) {
    prdError.value = true
    prdMessage.value = e.message || '上传失败'
  } finally {
    prdUploading.value = false
  }
}

async function uploadAttachments() {
  if (!attachFiles.value.length) return
  attachUploading.value = true
  attachMessage.value = ''
  attachError.value = false
  try {
    const res = await uploadProductAttachments(product.value, attachFiles.value)
    attachMessage.value = `已上传 ${res.paths?.length || 0} 个文件`
    attachFiles.value = []
    attachNames.value = []
    await loadAll()
  } catch (e) {
    attachError.value = true
    attachMessage.value = e.message || '上传失败'
  } finally {
    attachUploading.value = false
  }
}

watch(product, loadAll, { immediate: true })

onUnmounted(() => stopColdPoll())
</script>
