<template>
  <div class="min-h-screen bg-gray-50">
    <!-- Tab bar -->
    <div class="bg-white border-b border-gray-200 sticky top-0 z-10">
      <TabBar :product="product" :date="date" />
    </div>

    <div class="max-w-3xl mx-auto px-6 py-6">
      <!-- Header -->
      <div class="flex items-center gap-3 mb-6">
        <div>
          <h2 class="text-xl font-bold text-gray-900">{{ product }} · {{ date }}</h2>
          <p class="text-sm text-gray-500 mt-0.5">Pipeline 总览</p>
        </div>
        <div class="ml-auto">
          <span
            v-if="auditPassed === true"
            class="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-sm font-medium bg-green-100 text-green-700"
          >✅ 审核通过</span>
          <span
            v-else-if="auditPassed === false"
            class="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-sm font-medium bg-red-100 text-red-700"
          >❌ 审核未通过</span>
          <span
            v-else
            class="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-sm font-medium bg-gray-100 text-gray-600"
          >⏳ 进行中</span>
        </div>
      </div>

      <!-- Loading state -->
      <div v-if="loading" class="text-center py-12 text-gray-500">加载中...</div>
      <div v-else-if="loadError" class="bg-red-50 border border-red-200 rounded-xl p-4 text-red-700 text-sm">{{ loadError }}</div>

      <template v-else>
        <!-- Pipeline stages card -->
        <div class="bg-white rounded-xl shadow-sm border border-gray-200 mb-5">
          <div class="px-5 py-4 border-b border-gray-100">
            <h3 class="font-semibold text-gray-800">Pipeline 阶段</h3>
          </div>
          <div class="divide-y divide-gray-100">
            <div
              v-for="stage in stages"
              :key="stage.key"
              class="flex items-start gap-3 px-5 py-3.5"
            >
              <span class="text-lg mt-0.5 flex-shrink-0">{{ stage.icon }}</span>
              <div class="flex-1 min-w-0">
                <span class="font-medium text-gray-800 capitalize">{{ stage.label }}</span>
                <p v-if="stage.summary" class="text-sm text-gray-500 mt-0.5 truncate">{{ stage.summary }}</p>
                <p v-else class="text-sm text-gray-400 mt-0.5">尚未完成</p>
              </div>
            </div>
          </div>
        </div>

        <!-- Post summary card -->
        <div v-if="pkg" class="bg-white rounded-xl shadow-sm border border-gray-200">
          <div class="px-5 py-4 border-b border-gray-100">
            <h3 class="font-semibold text-gray-800">帖子摘要</h3>
          </div>
          <div class="p-5">
            <div class="flex gap-4">
              <!-- Cover thumbnail -->
              <div v-if="pkg.images && pkg.images.length > 0" class="flex-shrink-0">
                <img
                  :src="imageUrl(pkg.images[0].path)"
                  :alt="pkg.images[0].caption"
                  class="w-20 h-[107px] object-cover rounded-lg border border-gray-200"
                />
              </div>
              <!-- Content -->
              <div class="flex-1 min-w-0">
                <h4 class="font-semibold text-gray-900 text-base leading-tight mb-2">{{ pkg.title }}</h4>
                <p class="text-sm text-gray-600 leading-relaxed line-clamp-3">
                  {{ pkg.body ? pkg.body.slice(0, 100) + (pkg.body.length > 100 ? '...' : '') : '' }}
                </p>
                <div v-if="pkg.hashtags && pkg.hashtags.length" class="flex flex-wrap gap-1.5 mt-3">
                  <span
                    v-for="tag in pkg.hashtags"
                    :key="tag"
                    class="text-xs text-blue-600 bg-blue-50 px-2 py-0.5 rounded-full"
                  >{{ tag }}</span>
                </div>
              </div>
            </div>
            <!-- Action buttons -->
            <div class="flex gap-3 mt-4 pt-4 border-t border-gray-100">
              <router-link
                :to="`/${encodeURIComponent(product)}/${date}/post`"
                class="flex-1 text-center px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium rounded-lg transition-colors"
              >查看完整帖子</router-link>
              <router-link
                :to="`/${encodeURIComponent(product)}/${date}/audit`"
                class="flex-1 text-center px-4 py-2 bg-white hover:bg-gray-50 text-gray-700 text-sm font-medium rounded-lg border border-gray-200 transition-colors"
              >审核报告</router-link>
              <router-link
                :to="`/${encodeURIComponent(product)}/${date}/log`"
                class="flex-1 text-center px-4 py-2 bg-white hover:bg-gray-50 text-gray-700 text-sm font-medium rounded-lg border border-gray-200 transition-colors"
              >流水线日志</router-link>
            </div>
          </div>
        </div>
        <div v-else class="bg-white rounded-xl shadow-sm border border-gray-200 p-5 text-center text-gray-400 text-sm">
          帖子数据尚未生成
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { useRoute } from 'vue-router'
import TabBar from '../components/TabBar.vue'
import { getState, getPackage, imageUrl } from '../api/index.js'

const route = useRoute()
const product = computed(() => decodeURIComponent(route.params.product || ''))
const date = computed(() => route.params.date || '')

const state = ref(null)
const pkg = ref(null)
const loading = ref(true)
const loadError = ref(null)

const STAGE_LABELS = {
  planner: '规划师',
  scriptwriter: '文案创作',
  director: '素材编排',
  creator: '物料组装',
  audit: '审核'
}

const stages = computed(() => {
  if (!state.value) return []
  return ['planner', 'scriptwriter', 'director', 'creator', 'audit'].map(key => {
    const s = state.value[key] || {}
    let icon = '⏳'
    if (s.done) {
      icon = s.success ? '✅' : '❌'
    }
    return {
      key,
      label: STAGE_LABELS[key] || key,
      icon,
      summary: s.summary || null,
    }
  })
})

const auditPassed = computed(() => {
  if (!state.value?.audit?.done) return null
  return state.value.audit.success === true
})

async function load() {
  if (!product.value || !date.value) {
    loading.value = false
    return
  }
  loading.value = true
  loadError.value = null
  try {
    const [stateData, pkgData] = await Promise.allSettled([
      getState(product.value, date.value),
      getPackage(product.value, date.value),
    ])
    state.value = stateData.status === 'fulfilled' ? stateData.value : null
    pkg.value = pkgData.status === 'fulfilled' ? pkgData.value : null
    // Both null just means no pipeline has run yet for this date — not an error
  } catch (e) {
    loadError.value = e.message
  } finally {
    loading.value = false
  }
}

watch([product, date], load, { immediate: true })
</script>
