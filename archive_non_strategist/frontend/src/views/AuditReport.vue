<template>
  <div class="min-h-screen bg-gray-50">
    <!-- Tab bar -->
    <div class="bg-white border-b border-gray-200 sticky top-0 z-10">
      <TabBar :product="product" :date="date" />
    </div>

    <div class="max-w-4xl mx-auto px-6 py-6">
      <div v-if="loading" class="text-center py-12 text-gray-500">加载中...</div>
      <div v-else-if="loadError" class="bg-red-50 border border-red-200 rounded-xl p-4 text-red-700 text-sm">{{ loadError }}</div>

      <!-- Waiting for audit file while pipeline still running toward / in audit -->
      <div
        v-else-if="pipelineBeforeAudit"
        class="bg-amber-50 border border-amber-200 rounded-xl p-5 mb-5 text-amber-950"
      >
        <p class="font-semibold text-sm mb-1">流水线尚未到达审核</p>
        <p class="text-sm text-amber-900 leading-relaxed">
          当前阶段未完成 Creator。本页每 3 秒自动检查；进入审核后若耗时较长也会持续刷新。
        </p>
        <p v-if="silentRefreshing" class="text-xs text-amber-700 mt-2">正在拉取最新状态…</p>
      </div>

      <div
        v-else-if="auditPending"
        class="bg-blue-50 border border-blue-200 rounded-xl p-5 mb-5 text-blue-900"
      >
        <p class="font-semibold text-sm mb-1">审核进行中</p>
        <p class="text-sm text-blue-800 leading-relaxed">
          Creator 已完成，Audit 正在执行（含多轮视觉审核，可能持续数分钟）。
          本页每 3 秒自动刷新，无需手动整页刷新。
        </p>
        <p v-if="silentRefreshing" class="text-xs text-blue-600 mt-2">正在拉取最新状态…</p>
      </div>

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

        <div v-if="runHistoryAttempts.length" class="bg-white rounded-xl shadow-sm border border-gray-200 mb-5 p-4">
          <h3 class="font-semibold text-gray-800 mb-3">执行历史（完整 attempt）</h3>
          <div class="space-y-3">
            <div v-for="a in runHistoryAttempts" :key="a.attempt_id" class="border border-gray-200 rounded-lg p-3">
              <div class="flex flex-wrap items-center gap-2 text-sm mb-2">
                <span class="font-mono text-xs bg-gray-100 px-2 py-0.5 rounded">{{ a.attempt_id }}</span>
                <span class="text-gray-600">retry={{ a.retry_count ?? 0 }}</span>
                <span class="text-gray-600" v-if="a.started_at">{{ a.started_at }}</span>
                <span class="text-gray-400" v-if="a.ended_at">→ {{ a.ended_at }}</span>
                <span class="text-red-700" v-if="a.reviser?.route_to">route_to={{ a.reviser.route_to }}</span>
              </div>
              <div class="text-xs text-gray-700 space-y-1">
                <div v-for="s in a.steps || []" :key="`${a.attempt_id}-${s.step}`">
                  <span>{{ s.success ? '✅' : '❌' }} {{ s.step }}</span>
                  <span class="text-gray-500"> - {{ s.summary || s.error || '' }}</span>
                </div>
              </div>
              <div v-if="a.failed_items && a.failed_items.length" class="text-xs text-red-700 mt-2">
                失败条目：{{ a.failed_items.join(', ') }}
              </div>
              <div v-if="a.reviser?.revision_instructions" class="text-xs text-amber-800 mt-2 whitespace-pre-wrap">
                修订指令：{{ a.reviser.revision_instructions }}
              </div>
            </div>
          </div>
        </div>

        <!-- Items table -->
        <div class="bg-white rounded-xl shadow-sm border border-gray-200">
          <div class="px-5 py-4 border-b border-gray-100">
            <h3 class="font-semibold text-gray-800">条目明细（{{ audit.items?.length || 0 }} 项）</h3>
          </div>
          <div class="overflow-x-auto overflow-y-auto max-h-[60vh]">
            <table class="w-full">
              <thead>
                <tr class="bg-gray-50 border-b border-gray-200 sticky top-0 z-10">
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

      <div v-else class="bg-white rounded-xl shadow-sm border border-gray-200 p-8 text-center text-gray-500 text-sm">
        <p>暂无审核结果。</p>
        <p v-if="stateData && !stateData.creator?.done" class="mt-2 text-gray-400">
          流水线尚未完成 Creator，请稍后再打开本页。
        </p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, reactive, watch, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import TabBar from '../components/TabBar.vue'
import { getAudit, getFile, getState } from '../api/index.js'

const route = useRoute()
const product = computed(() => decodeURIComponent(route.params.product || ''))
const date = computed(() => route.params.date || '')

const audit = ref(null)
const revisionPlan = ref(null)
const stateData = ref(null)
const runHistory = ref(null)
const loading = ref(true)
const loadError = ref(null)
const silentRefreshing = ref(false)
const expandedItems = reactive(new Set())

let pollTimer = null

/** Creator finished, audit not marked done — waiting for audit_result.json */
const auditPending = computed(() => {
  if (loadError.value) return false
  if (audit.value) return false
  const s = stateData.value
  if (!s?.creator?.done) return false
  if (s.audit?.done === true) return false
  return true
})

/** Pipeline has not finished Creator yet; still poll so we pick up audit when ready */
const pipelineBeforeAudit = computed(() => {
  if (loadError.value) return false
  if (audit.value) return false
  const s = stateData.value
  if (!s) return false
  if (s.creator?.done) return false
  if (s.audit?.done === true) return false
  return true
})

/** Poll until we have audit JSON or state says audit.done (then load() sets error if file missing) */
const shouldPollForAudit = computed(() => {
  if (!product.value || !date.value) return false
  if (audit.value) return false
  if (loadError.value) return false
  const s = stateData.value
  if (!s) return false
  if (s.audit?.done === true) return false
  return true
})

const retryCount = computed(() => stateData.value?._retry_count ?? null)

const revisionAttempts = computed(() => {
  if (!revisionPlan.value) return []
  if (Array.isArray(revisionPlan.value)) return revisionPlan.value
  return []
})

const runHistoryAttempts = computed(() => {
  const arr = runHistory.value?.attempts
  if (!Array.isArray(arr)) return []
  return arr
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

function stopAuditPoll() {
  if (pollTimer != null) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

function startAuditPoll() {
  if (pollTimer != null) return
  pollTimer = setInterval(() => {
    load({ silent: true })
  }, 3000)
}

async function load(opts = {}) {
  const silent = Boolean(opts.silent)
  if (!silent) {
    loading.value = true
    loadError.value = null
    expandedItems.clear()
  } else {
    silentRefreshing.value = true
  }

  try {
    const [auditRes, stateRes] = await Promise.allSettled([
      getAudit(product.value, date.value),
      getState(product.value, date.value),
    ])

    const stateOk = stateRes.status === 'fulfilled'
    stateData.value = stateOk ? stateRes.value : null

    if (!stateOk) {
      audit.value = null
      loadError.value = '无法加载流水线状态（请确认日期与产品目录存在）'
      stopAuditPoll()
      return
    }

    if (auditRes.status === 'fulfilled' && auditRes.value) {
      audit.value = auditRes.value
      loadError.value = null
      stopAuditPoll()

      try {
        const revFile = await getFile(product.value, date.value, 'audit/revision_plan.json')
        revisionPlan.value = JSON.parse(revFile.content)
      } catch {
        revisionPlan.value = null
      }
      try {
        const h = await getFile(product.value, date.value, '.run_history.json')
        runHistory.value = JSON.parse(h.content)
      } catch {
        runHistory.value = null
      }
      return
    }

    audit.value = null
    revisionPlan.value = null
    try {
      const h = await getFile(product.value, date.value, '.run_history.json')
      runHistory.value = JSON.parse(h.content)
    } catch {
      runHistory.value = null
    }

    const st = stateData.value
    if (st.audit?.done === true) {
      loadError.value = '流水线显示审核已完成，但未找到 audit/audit_result.json（请检查文件是否被删除）'
      stopAuditPoll()
      return
    }

    loadError.value = null
  } catch (e) {
    if (!silent) loadError.value = e.message || String(e)
  } finally {
    if (!silent) loading.value = false
    silentRefreshing.value = false
  }
}

watch(
  () => [product.value, date.value],
  () => {
    stopAuditPoll()
    load({ silent: false })
  },
  { immediate: true }
)

watch(
  shouldPollForAudit,
  (v) => {
    if (v) startAuditPoll()
    else stopAuditPoll()
  },
  { immediate: true }
)

onUnmounted(() => {
  stopAuditPoll()
})
</script>
