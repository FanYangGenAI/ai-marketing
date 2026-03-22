<template>
  <div class="min-h-screen bg-gray-50">
    <!-- Tab bar -->
    <div class="bg-white border-b border-gray-200 sticky top-0 z-10">
      <TabBar :product="product" :date="date" />
    </div>

    <div class="max-w-4xl mx-auto px-6 py-6">
      <div v-if="loading" class="text-center py-12 text-gray-500">加载中...</div>
      <div v-else-if="loadError" class="bg-red-50 border border-red-200 rounded-xl p-4 text-red-700 text-sm">{{ loadError }}</div>

      <template v-else-if="audit">
        <!-- Overall result banner -->
        <div
          class="rounded-xl p-4 mb-5 flex items-center gap-3"
          :class="audit.passed ? 'bg-green-50 border border-green-200' : 'bg-red-50 border border-red-200'"
        >
          <span class="text-2xl">{{ audit.passed ? '✅' : '❌' }}</span>
          <div>
            <p class="font-semibold" :class="audit.passed ? 'text-green-800' : 'text-red-800'">
              审核{{ audit.passed ? '通过' : '未通过' }}
            </p>
            <p v-if="retryCount !== null" class="text-sm" :class="audit.passed ? 'text-green-600' : 'text-red-600'">
              共审核 {{ retryCount + 1 }} 次{{ retryCount > 0 ? `（${retryCount} 次重试后${audit.passed ? '通过' : '未通过'}）` : '' }}
            </p>
          </div>
        </div>

        <!-- Retry history -->
        <div v-if="revisionPlan" class="bg-white rounded-xl shadow-sm border border-gray-200 mb-5 p-4">
          <h3 class="font-semibold text-gray-800 mb-3">重试历史</h3>
          <div class="flex items-center gap-2 flex-wrap">
            <template v-for="(attempt, i) in revisionAttempts" :key="i">
              <div
                class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm border"
                :class="attempt.passed ? 'bg-green-50 border-green-200 text-green-700' : 'bg-red-50 border-red-200 text-red-700'"
              >
                <span>{{ attempt.passed ? '✅' : '❌' }}</span>
                <span>第{{ i + 1 }}次</span>
                <span v-if="attempt.route_to" class="text-xs opacity-70">→ {{ attempt.route_to }}</span>
              </div>
              <span v-if="i < revisionAttempts.length - 1" class="text-gray-400">→</span>
            </template>
          </div>
        </div>

        <!-- Items table -->
        <div class="bg-white rounded-xl shadow-sm border border-gray-200">
          <div class="px-5 py-4 border-b border-gray-100">
            <h3 class="font-semibold text-gray-800">条目明细（{{ audit.items?.length || 0 }} 项）</h3>
          </div>
          <div class="overflow-x-auto">
            <table class="w-full">
              <thead>
                <tr class="bg-gray-50 border-b border-gray-200">
                  <th class="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">条目</th>
                  <th class="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">类别</th>
                  <th class="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">投票</th>
                  <th class="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">结论</th>
                  <th class="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider min-w-[200px]">代表理由</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-gray-100">
                <template v-for="item in audit.items || []" :key="item.id">
                  <tr
                    class="hover:bg-gray-50 cursor-pointer transition-colors"
                    @click="toggleItem(item.id)"
                  >
                    <td class="px-4 py-3 font-mono text-sm text-gray-700">{{ item.id }}</td>
                    <td class="px-4 py-3">
                      <span
                        class="inline-flex px-2 py-0.5 rounded-full text-xs font-medium"
                        :class="categoryClass(item.category)"
                      >{{ item.category }}</span>
                    </td>
                    <td class="px-4 py-3 text-sm text-gray-700">
                      <span class="text-green-600 font-medium">{{ item.votes?.pass || 0 }}通</span>
                      /
                      <span class="text-red-500 font-medium">{{ item.votes?.fail || 0 }}失</span>
                    </td>
                    <td class="px-4 py-3">
                      <span class="text-lg">{{ item.passed ? '✅' : '❌' }}</span>
                    </td>
                    <td class="px-4 py-3 text-sm text-gray-600">
                      <span class="line-clamp-2">{{ item.reason }}</span>
                    </td>
                  </tr>
                  <!-- Expanded row -->
                  <tr v-if="expandedItems.has(item.id)" class="bg-blue-50/50">
                    <td colspan="5" class="px-4 py-3">
                      <div class="text-xs font-semibold text-gray-500 mb-2 uppercase tracking-wider">Auditor 三票明细</div>
                      <div class="space-y-1.5">
                        <div
                          v-for="(reason, idx) in item.all_reasons || []"
                          :key="idx"
                          class="flex gap-2 text-sm"
                        >
                          <span class="text-gray-400 font-medium flex-shrink-0 w-18">
                            Auditor {{ ['A', 'B', 'C'][idx] || idx + 1 }}：
                          </span>
                          <span class="text-gray-700">{{ reason }}</span>
                        </div>
                      </div>
                    </td>
                  </tr>
                </template>
              </tbody>
            </table>
          </div>
        </div>
      </template>

      <div v-else class="bg-white rounded-xl shadow-sm border border-gray-200 p-8 text-center text-gray-400">
        暂无审核数据
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, reactive, watch } from 'vue'
import { useRoute } from 'vue-router'
import TabBar from '../components/TabBar.vue'
import { getAudit, getFile, getState } from '../api/index.js'

const route = useRoute()
const product = computed(() => decodeURIComponent(route.params.product || ''))
const date = computed(() => route.params.date || '')

const audit = ref(null)
const revisionPlan = ref(null)
const stateData = ref(null)
const loading = ref(true)
const loadError = ref(null)
const expandedItems = reactive(new Set())

const retryCount = computed(() => stateData.value?._retry_count ?? null)

const revisionAttempts = computed(() => {
  if (!revisionPlan.value) return []
  if (Array.isArray(revisionPlan.value)) return revisionPlan.value
  return []
})

function categoryClass(cat) {
  switch (cat) {
    case 'platform': return 'bg-blue-100 text-blue-700'
    case 'content': return 'bg-purple-100 text-purple-700'
    case 'safety': return 'bg-red-100 text-red-700'
    default: return 'bg-gray-100 text-gray-600'
  }
}

function toggleItem(id) {
  if (expandedItems.has(id)) {
    expandedItems.delete(id)
  } else {
    expandedItems.add(id)
  }
}

async function load() {
  loading.value = true
  loadError.value = null
  expandedItems.clear()
  try {
    const [auditRes, stateRes] = await Promise.allSettled([
      getAudit(product.value, date.value),
      getState(product.value, date.value),
    ])
    audit.value = auditRes.status === 'fulfilled' ? auditRes.value : null
    stateData.value = stateRes.status === 'fulfilled' ? stateRes.value : null

    if (!audit.value) {
      loadError.value = '无法加载审核数据'
    }

    // Try to load revision_plan.json
    try {
      const revFile = await getFile(product.value, date.value, 'audit/revision_plan.json')
      revisionPlan.value = JSON.parse(revFile.content)
    } catch {
      revisionPlan.value = null
    }
  } catch (e) {
    loadError.value = e.message
  } finally {
    loading.value = false
  }
}

watch([product, date], load, { immediate: true })
</script>
