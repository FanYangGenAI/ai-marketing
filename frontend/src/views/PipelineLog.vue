<template>
  <div class="min-h-screen bg-gray-50">
    <!-- Tab bar -->
    <div class="bg-white border-b border-gray-200 sticky top-0 z-10">
      <TabBar :product="product" :date="date" />
    </div>

    <div class="flex gap-0 max-w-6xl mx-auto">
      <!-- Left: accordion stage list -->
      <div class="w-72 flex-shrink-0 border-r border-gray-200 min-h-screen bg-white">
        <div class="px-4 py-4 border-b border-gray-100">
          <h3 class="font-semibold text-gray-800">流水线阶段</h3>
        </div>

        <div v-if="loading" class="px-4 py-4 text-sm text-gray-400">加载中...</div>

        <div v-for="stage in stages" :key="stage.key" class="border-b border-gray-100 last:border-0">
          <!-- Stage header -->
          <button
            @click="toggleStage(stage.key)"
            class="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-gray-50 transition-colors"
          >
            <span class="text-base">{{ stage.icon }}</span>
            <div class="flex-1 min-w-0">
              <span class="font-medium text-gray-800 text-sm">{{ stage.label }}</span>
              <p v-if="stage.time" class="text-xs text-gray-400 mt-0.5 truncate">{{ stage.time }}</p>
            </div>
            <svg
              class="w-4 h-4 text-gray-400 flex-shrink-0 transition-transform"
              :class="expandedStages.has(stage.key) ? 'rotate-90' : ''"
              fill="none" stroke="currentColor" viewBox="0 0 24 24"
            >
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"/>
            </svg>
          </button>

          <!-- Files list -->
          <div v-if="expandedStages.has(stage.key)" class="bg-gray-50 border-t border-gray-100">
            <button
              v-for="file in stage.files"
              :key="file.path"
              @click="loadFile(file)"
              class="w-full flex items-center gap-2 px-6 py-2 text-left hover:bg-blue-50 transition-colors"
              :class="selectedFile?.path === file.path ? 'bg-blue-50 text-blue-700' : 'text-gray-600'"
            >
              <span class="text-xs">{{ file.icon }}</span>
              <span class="text-xs truncate">{{ file.label }}</span>
            </button>
          </div>
        </div>
      </div>

      <!-- Right: file content viewer -->
      <div class="flex-1 min-w-0 p-6">
        <div v-if="!selectedFile" class="flex items-center justify-center h-64 text-gray-400 text-sm">
          ← 选择左侧文件查看内容
        </div>
        <div v-else-if="fileLoading" class="flex items-center justify-center h-64 text-gray-400 text-sm">
          加载中...
        </div>
        <div v-else-if="fileError" class="bg-red-50 border border-red-200 rounded-xl p-4 text-red-700 text-sm">
          {{ fileError }}
        </div>
        <div v-else-if="fileContent">
          <!-- Header -->
          <div class="flex items-center gap-2 mb-4">
            <span class="text-base">{{ selectedFile.icon }}</span>
            <h4 class="font-semibold text-gray-800">{{ selectedFile.label }}</h4>
            <span class="ml-auto text-xs text-gray-400 bg-gray-100 px-2 py-0.5 rounded">{{ fileContent.type }}</span>
          </div>
          <!-- Content -->
          <div class="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
            <!-- Markdown -->
            <div
              v-if="fileContent.type === 'markdown'"
              class="prose px-6 py-5 max-w-none text-sm max-h-[70vh] overflow-y-auto"
              v-html="renderedMarkdown"
            />
            <!-- JSON -->
            <pre
              v-else-if="fileContent.type === 'json'"
              class="p-5 text-xs overflow-x-auto overflow-y-auto bg-gray-900 text-gray-100 rounded-xl m-0 max-h-[70vh]"
              v-html="renderedJson"
            />
            <!-- Plain text -->
            <pre v-else class="p-5 text-xs overflow-x-auto overflow-y-auto whitespace-pre-wrap bg-gray-50 rounded-xl m-0 text-gray-700 max-h-[70vh]">{{ fileContent.content }}</pre>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, reactive, watch } from 'vue'
import { useRoute } from 'vue-router'
import { marked } from 'marked'
import TabBar from '../components/TabBar.vue'
import { getState, getFile } from '../api/index.js'

const route = useRoute()
const product = computed(() => decodeURIComponent(route.params.product || ''))
const date = computed(() => route.params.date || '')

const stateData = ref(null)
const loading = ref(true)
const expandedStages = reactive(new Set())
const selectedFile = ref(null)
const fileContent = ref(null)
const fileLoading = ref(false)
const fileError = ref(null)

const STAGE_CONFIG = [
  {
    key: 'planner',
    label: '规划师 (Planner)',
    files: [
      { path: 'plan/daily_marketing_plan.md', label: 'daily_marketing_plan.md', icon: '📄' },
      { path: 'plan/debate_raw.md', label: 'debate_raw.md', icon: '💬' },
    ]
  },
  {
    key: 'scriptwriter',
    label: '文案 (Scriptwriter)',
    files: [
      { path: 'script/daily_marketing_script.md', label: 'daily_marketing_script.md', icon: '📄' },
      { path: 'script/debate_raw.md', label: 'debate_raw.md', icon: '💬' },
    ]
  },
  {
    key: 'director',
    label: '编排 (Director)',
    files: [
      { path: 'director/director_task_result.json', label: 'director_task_result.json', icon: '📋' },
      { path: 'director/director_raw.md', label: 'director_raw.md', icon: '📝' },
    ]
  },
  {
    key: 'creator',
    label: '组装 (Creator)',
    files: [
      { path: 'creator/post_content.md', label: 'post_content.md', icon: '📄' },
      { path: 'creator/creator_raw.md', label: 'creator_raw.md', icon: '📝' },
    ]
  },
  {
    key: 'audit',
    label: '审核 (Audit)',
    files: [
      { path: 'audit/audit_raw.md', label: 'audit_raw.md', icon: '📝' },
      { path: 'audit/audit_result.json', label: 'audit_result.json', icon: '📋' },
    ]
  },
]

const stages = computed(() => {
  return STAGE_CONFIG.map(config => {
    const s = stateData.value?.[config.key] || {}
    let icon = '⏳'
    if (s.done) icon = s.success ? '✅' : '❌'
    return {
      ...config,
      icon,
      time: s.timestamp || null,
    }
  })
})

const renderedMarkdown = computed(() => {
  if (!fileContent.value || fileContent.value.type !== 'markdown') return ''
  return marked.parse(fileContent.value.content || '')
})

function syntaxHighlightJson(json) {
  // Simple manual JSON syntax coloring
  return json
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(
      /("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+\-]?\d+)?)/g,
      match => {
        let cls = 'json-number'
        if (/^"/.test(match)) {
          if (/:$/.test(match)) {
            cls = 'json-key'
          } else {
            cls = 'json-string'
          }
        } else if (/true|false/.test(match)) {
          cls = 'json-boolean'
        } else if (/null/.test(match)) {
          cls = 'json-null'
        }
        return `<span class="${cls}">${match}</span>`
      }
    )
}

const renderedJson = computed(() => {
  if (!fileContent.value || fileContent.value.type !== 'json') return ''
  try {
    const obj = JSON.parse(fileContent.value.content)
    const pretty = JSON.stringify(obj, null, 2)
    return syntaxHighlightJson(pretty)
  } catch {
    return fileContent.value.content
  }
})

function toggleStage(key) {
  if (expandedStages.has(key)) {
    expandedStages.delete(key)
  } else {
    expandedStages.add(key)
  }
}

async function loadFile(file) {
  selectedFile.value = file
  fileContent.value = null
  fileError.value = null
  fileLoading.value = true
  try {
    fileContent.value = await getFile(product.value, date.value, file.path)
  } catch (e) {
    fileError.value = `无法加载文件: ${e.message}`
  } finally {
    fileLoading.value = false
  }
}

async function load() {
  loading.value = true
  selectedFile.value = null
  fileContent.value = null
  expandedStages.clear()
  try {
    stateData.value = await getState(product.value, date.value)
  } catch {
    stateData.value = null
  } finally {
    loading.value = false
  }
}

watch([product, date], load, { immediate: true })
</script>
