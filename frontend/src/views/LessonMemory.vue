<template>
  <div class="min-h-screen bg-gray-50">
    <!-- Header -->
    <div class="bg-white border-b border-gray-200 px-6 py-4">
      <div class="flex items-center gap-4 flex-wrap">
        <h2 class="text-lg font-bold text-gray-900">{{ product }} — 经验记忆</h2>
        <div class="flex gap-1 ml-auto">
          <button
            v-for="p in platforms"
            :key="p"
            @click="activePlatform = p"
            class="px-3 py-1.5 text-sm rounded-lg font-medium transition-colors"
            :class="activePlatform === p
              ? 'bg-blue-600 text-white'
              : 'bg-gray-100 text-gray-600 hover:bg-gray-200'"
          >{{ p }}</button>
        </div>
      </div>
    </div>

    <div class="max-w-5xl mx-auto px-6 py-6">
      <div v-if="loading" class="text-center py-12 text-gray-500">加载中...</div>
      <div v-else-if="loadError" class="bg-red-50 border border-red-200 rounded-xl p-4 text-red-700 text-sm">{{ loadError }}</div>

      <template v-else-if="lessons.length > 0">
        <!-- Summary stats -->
        <div class="flex items-center gap-4 mb-5">
          <p class="text-sm text-gray-500">共 <span class="font-semibold text-gray-800">{{ lessons.length }}</span> 条经验</p>
          <div class="flex gap-2 flex-wrap">
            <span v-for="cat in categories" :key="cat"
              class="text-xs px-2 py-0.5 rounded-full"
              :class="categoryClass(cat)"
            >{{ cat }}: {{ lessonsByCategory[cat] }}</span>
          </div>
        </div>

        <!-- Lessons table -->
        <div class="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
          <table class="w-full">
            <thead>
              <tr class="bg-gray-50 border-b border-gray-200">
                <th class="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">条目</th>
                <th class="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">类别</th>
                <th class="text-center px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">违规次数</th>
                <th class="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider min-w-[280px]">规则摘要</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-gray-100">
              <template v-for="lesson in lessons" :key="lesson.id">
                <tr
                  class="hover:bg-gray-50 cursor-pointer transition-colors"
                  @click="toggleLesson(lesson.id)"
                >
                  <td class="px-4 py-3 font-mono text-sm text-gray-700">{{ lesson.checklist_item }}</td>
                  <td class="px-4 py-3">
                    <span class="inline-flex px-2 py-0.5 rounded-full text-xs font-medium" :class="categoryClass(lesson.category)">
                      {{ lesson.category }}
                    </span>
                  </td>
                  <td class="px-4 py-3 text-center">
                    <span
                      class="inline-flex items-center justify-center w-7 h-7 rounded-full text-sm font-bold"
                      :class="lesson.fail_count >= 3 ? 'bg-red-100 text-red-700' : lesson.fail_count >= 2 ? 'bg-orange-100 text-orange-700' : 'bg-yellow-100 text-yellow-700'"
                    >{{ lesson.fail_count }}</span>
                  </td>
                  <td class="px-4 py-3 text-sm text-gray-600">
                    <span class="line-clamp-2">{{ truncateRule(lesson.rule) }}</span>
                  </td>
                </tr>
                <!-- Expanded row -->
                <tr v-if="expandedLessons.has(lesson.id)" class="bg-blue-50/40">
                  <td colspan="4" class="px-4 py-4">
                    <div class="grid grid-cols-1 gap-3">
                      <div>
                        <p class="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1">完整规则</p>
                        <p class="text-sm text-gray-700 leading-relaxed">{{ lesson.rule }}</p>
                      </div>
                      <div v-if="lesson.offending_example">
                        <p class="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1">违规示例</p>
                        <p class="text-sm text-red-700 bg-red-50 px-3 py-2 rounded-lg border border-red-100 leading-relaxed">{{ lesson.offending_example }}</p>
                      </div>
                      <div v-if="lesson.date" class="text-xs text-gray-400">记录日期：{{ lesson.date }}</div>
                    </div>
                  </td>
                </tr>
              </template>
            </tbody>
          </table>
        </div>
      </template>

      <div v-else class="bg-white rounded-xl shadow-sm border border-gray-200 p-8 text-center text-gray-400">
        暂无 {{ activePlatform }} 平台的经验记忆
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, reactive, watch } from 'vue'
import { useRoute } from 'vue-router'
import { getMemory } from '../api/index.js'

const route = useRoute()
const product = computed(() => decodeURIComponent(route.params.product || ''))

const memoryData = ref(null)
const loading = ref(true)
const loadError = ref(null)
const activePlatform = ref('xiaohongshu')
const expandedLessons = reactive(new Set())

const platforms = ['xiaohongshu']

const lessons = computed(() => memoryData.value?.lessons || [])

const categories = computed(() => {
  const cats = new Set(lessons.value.map(l => l.category))
  return [...cats]
})

const lessonsByCategory = computed(() => {
  const counts = {}
  lessons.value.forEach(l => {
    counts[l.category] = (counts[l.category] || 0) + 1
  })
  return counts
})

function categoryClass(cat) {
  switch (cat) {
    case 'platform': return 'bg-blue-100 text-blue-700'
    case 'content': return 'bg-purple-100 text-purple-700'
    case 'safety': return 'bg-red-100 text-red-700'
    default: return 'bg-gray-100 text-gray-600'
  }
}

function truncateRule(rule) {
  if (!rule) return ''
  const firstSentence = rule.split('。')[0]
  return firstSentence.length > 60 ? firstSentence.slice(0, 60) + '...' : firstSentence
}

function toggleLesson(id) {
  if (expandedLessons.has(id)) {
    expandedLessons.delete(id)
  } else {
    expandedLessons.add(id)
  }
}

async function load() {
  loading.value = true
  loadError.value = null
  expandedLessons.clear()
  try {
    memoryData.value = await getMemory(product.value, activePlatform.value)
  } catch (e) {
    if (e.message.includes('404')) {
      memoryData.value = null
      loadError.value = null
    } else {
      loadError.value = '无法加载经验记忆：' + e.message
    }
  } finally {
    loading.value = false
  }
}

watch([product, activePlatform], load, { immediate: true })
</script>
