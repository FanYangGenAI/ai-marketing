<template>
  <div class="min-h-screen bg-gray-50">
    <!-- Tab bar -->
    <div class="bg-white border-b border-gray-200 sticky top-0 z-10">
      <TabBar :product="product" :date="date" />
    </div>

    <div v-if="loading" class="text-center py-12 text-gray-500">加载中...</div>
    <div v-else-if="loadError" class="max-w-3xl mx-auto px-6 py-6">
      <div class="bg-red-50 border border-red-200 rounded-xl p-4 text-red-700 text-sm">{{ loadError }}</div>
    </div>

    <div v-else class="px-6 py-6">
      <div class="flex flex-col lg:flex-row gap-6 max-w-5xl mx-auto">
        <!-- Left: XHS-style post card -->
        <div class="lg:w-[370px] flex-shrink-0">
          <div class="bg-white rounded-2xl shadow-lg border border-gray-100 overflow-hidden max-w-[370px] mx-auto">
            <!-- Image carousel -->
            <ImageCarousel
              :images="pkg.images || []"
              @open-lightbox="openLightbox"
            />

            <!-- Post content -->
            <div class="px-4 py-4">
              <h3 class="font-semibold text-gray-900 text-base leading-tight mb-3">
                {{ pkg.title }}
              </h3>
              <div class="text-sm text-gray-700 leading-relaxed">
                <p :class="bodyExpanded ? '' : 'line-clamp-5'">{{ pkg.body }}</p>
                <button
                  v-if="!bodyExpanded && pkg.body && pkg.body.length > 200"
                  @click="bodyExpanded = true"
                  class="text-blue-500 text-xs mt-1 hover:underline"
                >展开全文</button>
                <button
                  v-if="bodyExpanded"
                  @click="bodyExpanded = false"
                  class="text-blue-500 text-xs mt-1 hover:underline"
                >收起</button>
              </div>
              <div v-if="pkg.hashtags && pkg.hashtags.length" class="flex flex-wrap gap-1 mt-3">
                <span
                  v-for="tag in pkg.hashtags"
                  :key="tag"
                  class="text-xs text-blue-500"
                >{{ tag }}</span>
              </div>
            </div>
          </div>
        </div>

        <!-- Right panel -->
        <div class="flex-1 min-w-0 space-y-5">
          <!-- Image list -->
          <div class="bg-white rounded-xl shadow-sm border border-gray-200">
            <div class="px-5 py-3 border-b border-gray-100">
              <h3 class="font-semibold text-gray-800">图片列表</h3>
            </div>
            <div class="divide-y divide-gray-100">
              <div
                v-for="img in pkg.images || []"
                :key="img.order"
                class="flex items-center gap-3 px-5 py-3"
              >
                <span class="text-sm font-mono text-gray-400 w-6 flex-shrink-0">{{ img.order }}</span>
                <img
                  :src="imageUrl(img.path)"
                  :alt="img.caption"
                  class="w-12 h-16 object-cover rounded border border-gray-200 flex-shrink-0 cursor-pointer hover:opacity-80 transition-opacity"
                  @click="openLightboxByIndex(img.order - 1)"
                />
                <span class="flex-1 text-sm text-gray-700 min-w-0 truncate">{{ img.caption }}</span>
                <a
                  :href="imageUrl(img.path)"
                  :download="`img_${String(img.order).padStart(2, '0')}.png`"
                  class="flex-shrink-0 flex items-center gap-1 text-sm text-blue-600 hover:text-blue-700 px-3 py-1 border border-blue-200 rounded-lg hover:bg-blue-50 transition-colors"
                >
                  <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/>
                  </svg>
                  下载
                </a>
              </div>
              <div v-if="!pkg.images || pkg.images.length === 0" class="px-5 py-4 text-sm text-gray-400">
                暂无图片
              </div>
            </div>
          </div>

          <!-- Copy actions -->
          <div class="bg-white rounded-xl shadow-sm border border-gray-200">
            <div class="px-5 py-3 border-b border-gray-100">
              <h3 class="font-semibold text-gray-800">文案操作</h3>
            </div>
            <div class="px-5 py-4 flex flex-wrap gap-3">
              <button
                @click="copyText('title', pkg.title)"
                class="flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg border transition-colors"
                :class="copiedKey === 'title' ? 'bg-green-50 border-green-300 text-green-700' : 'border-gray-200 text-gray-700 hover:bg-gray-50'"
              >
                <span v-if="copiedKey === 'title'">✓ 已复制</span>
                <span v-else>复制标题</span>
              </button>
              <button
                @click="copyText('body', pkg.body)"
                class="flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg border transition-colors"
                :class="copiedKey === 'body' ? 'bg-green-50 border-green-300 text-green-700' : 'border-gray-200 text-gray-700 hover:bg-gray-50'"
              >
                <span v-if="copiedKey === 'body'">✓ 已复制</span>
                <span v-else>复制正文</span>
              </button>
              <button
                @click="copyText('hashtags', (pkg.hashtags || []).join(' '))"
                class="flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg border transition-colors"
                :class="copiedKey === 'hashtags' ? 'bg-green-50 border-green-300 text-green-700' : 'border-gray-200 text-gray-700 hover:bg-gray-50'"
              >
                <span v-if="copiedKey === 'hashtags'">✓ 已复制</span>
                <span v-else>复制话题标签</span>
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Lightbox -->
    <Teleport to="body">
      <div
        v-if="lightboxOpen"
        class="fixed inset-0 bg-black/90 z-50 flex items-center justify-center"
        @click.self="lightboxOpen = false"
      >
        <button
          @click="lightboxOpen = false"
          class="absolute top-4 right-4 text-white/80 hover:text-white text-3xl leading-none w-10 h-10 flex items-center justify-center"
          aria-label="关闭"
        >&times;</button>
        <button
          v-if="lightboxImages.length > 1"
          @click="prevLightbox"
          class="absolute left-4 top-1/2 -translate-y-1/2 w-10 h-10 bg-white/20 hover:bg-white/30 text-white rounded-full flex items-center justify-center"
        >
          <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M15 19l-7-7 7-7"/>
          </svg>
        </button>
        <img
          :src="imageUrl(lightboxImages[lightboxIndex]?.path)"
          :alt="lightboxImages[lightboxIndex]?.caption || ''"
          class="max-w-[90vw] max-h-[90vh] object-contain rounded-lg shadow-2xl"
        />
        <button
          v-if="lightboxImages.length > 1"
          @click="nextLightbox"
          class="absolute right-4 top-1/2 -translate-y-1/2 w-10 h-10 bg-white/20 hover:bg-white/30 text-white rounded-full flex items-center justify-center"
        >
          <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M9 5l7 7-7 7"/>
          </svg>
        </button>
        <div class="absolute bottom-4 left-1/2 -translate-x-1/2 text-white/70 text-sm">
          {{ lightboxIndex + 1 }} / {{ lightboxImages.length }}
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { useRoute } from 'vue-router'
import TabBar from '../components/TabBar.vue'
import ImageCarousel from '../components/ImageCarousel.vue'
import { getPackage, imageUrl } from '../api/index.js'

const route = useRoute()
const product = computed(() => decodeURIComponent(route.params.product || ''))
const date = computed(() => route.params.date || '')

const pkg = ref(null)
const loading = ref(true)
const loadError = ref(null)
const bodyExpanded = ref(false)
const copiedKey = ref(null)
let copyTimer = null

// Lightbox state
const lightboxOpen = ref(false)
const lightboxIndex = ref(0)
const lightboxImages = computed(() => pkg.value?.images || [])

function openLightbox(index) {
  lightboxIndex.value = index
  lightboxOpen.value = true
}

function openLightboxByIndex(index) {
  lightboxIndex.value = index
  lightboxOpen.value = true
}

function prevLightbox() {
  lightboxIndex.value = (lightboxIndex.value - 1 + lightboxImages.value.length) % lightboxImages.value.length
}

function nextLightbox() {
  lightboxIndex.value = (lightboxIndex.value + 1) % lightboxImages.value.length
}

async function copyText(key, text) {
  if (!text) return
  try {
    await navigator.clipboard.writeText(text)
    copiedKey.value = key
    if (copyTimer) clearTimeout(copyTimer)
    copyTimer = setTimeout(() => { copiedKey.value = null }, 1500)
  } catch (e) {
    console.error('Copy failed:', e)
  }
}

async function load() {
  loading.value = true
  loadError.value = null
  bodyExpanded.value = false
  try {
    pkg.value = await getPackage(product.value, date.value)
  } catch (e) {
    loadError.value = '无法加载帖子数据：' + e.message
  } finally {
    loading.value = false
  }
}

watch([product, date], load, { immediate: true })
</script>
