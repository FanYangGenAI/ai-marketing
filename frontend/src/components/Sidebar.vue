<template>
  <aside class="w-60 bg-gray-900 text-gray-100 flex flex-col h-screen overflow-hidden">
    <!-- Header -->
    <div class="px-4 py-4 border-b border-gray-700 flex-shrink-0">
      <h1 class="text-base font-bold text-white tracking-wide">AI Marketing</h1>
      <p class="text-xs text-gray-400 mt-0.5">Studio</p>
    </div>

    <!-- Products list -->
    <nav class="flex-1 overflow-y-auto py-2">
      <div v-if="loading" class="px-4 py-3 text-sm text-gray-400">加载中...</div>
      <div v-else-if="error" class="px-4 py-3 text-sm text-red-400">{{ error }}</div>

      <div v-for="product in products" :key="product" class="mb-1">
        <!-- Product header row -->
        <button
          @click="toggleProduct(product)"
          class="w-full flex items-center justify-between px-4 py-2 text-sm font-semibold text-gray-200 hover:bg-gray-800 transition-colors"
        >
          <span class="truncate">{{ product }}</span>
          <svg
            class="w-4 h-4 flex-shrink-0 transition-transform"
            :class="expandedProducts.has(product) ? 'rotate-90' : ''"
            fill="none" stroke="currentColor" viewBox="0 0 24 24"
          >
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"/>
          </svg>
        </button>

        <!-- Date list -->
        <div v-if="expandedProducts.has(product)" class="ml-2">
          <div
            v-if="!datesByProduct[product]"
            class="px-4 py-1 text-xs text-gray-500"
          >加载中...</div>

          <router-link
            v-for="entry in (datesByProduct[product] || [])"
            :key="entry.date"
            :to="`/${encodeURIComponent(product)}/${entry.date}`"
            class="flex items-center px-3 py-1.5 text-xs rounded mx-1 transition-colors"
            :class="isActiveDate(product, entry.date)
              ? 'bg-blue-600 text-white'
              : 'text-gray-300 hover:bg-gray-700'"
          >
            <span class="mr-2 text-sm">{{ statusIcon(entry.audit_passed) }}</span>
            <span>{{ entry.date }}</span>
            <span class="ml-auto text-gray-400 text-xs">{{ entry.stages_done }}/5</span>
          </router-link>
        </div>
      </div>
    </nav>

    <!-- Bottom: product-level links (shown for active product) -->
    <div class="border-t border-gray-700 flex-shrink-0 py-2">
      <template v-if="activeProduct">
        <div class="px-3 mb-1">
          <p class="text-xs text-gray-500 uppercase tracking-wider px-1 mb-1">{{ activeProduct }}</p>
          <router-link
            :to="`/${encodeURIComponent(activeProduct)}/assets`"
            class="flex items-center gap-2 px-3 py-2 text-sm rounded transition-colors"
            :class="$route.path.endsWith('/assets')
              ? 'bg-blue-600 text-white'
              : 'text-gray-300 hover:bg-gray-700'"
          >
            <span>🖼</span> 素材库
          </router-link>
          <router-link
            :to="`/${encodeURIComponent(activeProduct)}/memory`"
            class="flex items-center gap-2 px-3 py-2 text-sm rounded transition-colors"
            :class="$route.path.endsWith('/memory')
              ? 'bg-blue-600 text-white'
              : 'text-gray-300 hover:bg-gray-700'"
          >
            <span>🧠</span> 经验记忆
          </router-link>
        </div>
      </template>
      <div v-else class="px-4 py-2 text-xs text-gray-500">选择产品查看</div>
    </div>
  </aside>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getProducts, getDates } from '../api/index.js'

const route = useRoute()
const router = useRouter()

const products = ref([])
const loading = ref(true)
const error = ref(null)
const expandedProducts = reactive(new Set())
const datesByProduct = reactive({})

const activeProduct = computed(() => {
  const params = route.params
  return params.product ? decodeURIComponent(params.product) : null
})

function statusIcon(auditPassed) {
  if (auditPassed === true) return '✅'
  if (auditPassed === false) return '❌'
  return '⏳'
}

function isActiveDate(product, date) {
  if (!route.params.product || !route.params.date) return false
  const routeProduct = decodeURIComponent(route.params.product)
  return routeProduct === product && route.params.date === date
}

async function toggleProduct(product) {
  if (expandedProducts.has(product)) {
    expandedProducts.delete(product)
  } else {
    expandedProducts.add(product)
    if (!datesByProduct[product]) {
      await loadDates(product)
    }
  }
}

async function loadDates(product) {
  try {
    datesByProduct[product] = await getDates(product)
  } catch (e) {
    datesByProduct[product] = []
    console.error(`Failed to load dates for ${product}:`, e)
  }
}

onMounted(async () => {
  try {
    products.value = await getProducts()
    if (products.value.length > 0) {
      const first = products.value[0]
      expandedProducts.add(first)
      await loadDates(first)

      // Navigate to first date if on root
      if (route.path === '/' || route.path === '/products') {
        const dates = datesByProduct[first]
        if (dates && dates.length > 0) {
          router.push(`/${encodeURIComponent(first)}/${dates[0].date}`)
        }
      }
    }
  } catch (e) {
    error.value = '无法加载产品列表'
    console.error(e)
  } finally {
    loading.value = false
  }
})

// When navigating to a product, auto-expand it
watch(activeProduct, async (product) => {
  if (product && !expandedProducts.has(product)) {
    expandedProducts.add(product)
    if (!datesByProduct[product]) {
      await loadDates(product)
    }
  }
}, { immediate: true })
</script>
