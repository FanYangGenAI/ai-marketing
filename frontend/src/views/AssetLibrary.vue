<template>
  <div class="min-h-screen bg-gray-50">
    <!-- Header -->
    <div class="bg-white border-b border-gray-200 px-6 py-4">
      <div class="flex items-center gap-3">
        <h2 class="text-lg font-bold text-gray-900">{{ product }} — 素材库</h2>
        <span class="text-sm text-gray-500">共 {{ filteredAssets.length }} 个素材</span>
      </div>
    </div>

    <!-- Filter bar -->
    <div class="bg-white border-b border-gray-200 px-6 py-3 flex items-center gap-4 flex-wrap">
      <div class="flex gap-1">
        <button
          v-for="src in ['全部', 'generate', 'screenshot', 'reuse', 'user_upload']"
          :key="src"
          @click="filterSource = src"
          class="px-3 py-1.5 text-sm rounded-lg font-medium transition-colors"
          :class="filterSource === src
            ? 'bg-blue-600 text-white'
            : 'bg-gray-100 text-gray-600 hover:bg-gray-200'"
        >{{ src }}</button>
      </div>
      <input
        v-model="searchQuery"
        type="text"
        placeholder="搜索 prompt..."
        class="ml-auto px-3 py-1.5 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 w-52"
      />
    </div>

    <div v-if="loading" class="text-center py-12 text-gray-500">加载中...</div>
    <div v-else-if="loadError" class="max-w-3xl mx-auto px-6 py-6">
      <div class="bg-red-50 border border-red-200 rounded-xl p-4 text-red-700 text-sm">{{ loadError }}</div>
    </div>

    <div v-else class="px-6 py-6">
      <div v-if="filteredAssets.length === 0" class="text-center py-12 text-gray-400">
        没有匹配的素材
      </div>

      <!-- Image grid -->
      <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
        <div
          v-for="asset in filteredAssets"
          :key="asset.id"
          @click="selectedAsset = asset"
          class="group relative bg-white rounded-xl border border-gray-200 overflow-hidden cursor-pointer hover:shadow-md transition-shadow"
        >
          <button
            type="button"
            class="absolute top-2 right-2 z-10 px-2 py-1 text-xs rounded-md bg-red-600/90 hover:bg-red-700 text-white shadow disabled:opacity-50 opacity-0 pointer-events-none group-hover:opacity-100 group-hover:pointer-events-auto transition-opacity"
            :disabled="deleting"
            @click.stop="removeAssetById(asset.id)"
          >
            删除
          </button>
          <!-- Thumbnail -->
          <div class="aspect-[3/4] bg-gray-100 overflow-hidden">
            <img
              :src="assetImageUrl(asset)"
              :alt="asset.prompt || asset.id"
              class="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
              loading="lazy"
            />
          </div>
          <!-- Info -->
          <div class="p-2">
            <div class="flex items-center justify-between gap-1">
              <span
                class="text-xs px-1.5 py-0.5 rounded font-medium"
                :class="sourceClass(asset.source)"
              >{{ asset.source }}</span>
              <span class="text-xs text-gray-400">{{ asset.created_at }}</span>
            </div>
            <p v-if="asset.note" class="text-[10px] text-gray-500 mt-1 line-clamp-2">{{ asset.note }}</p>
          </div>
        </div>
      </div>
    </div>

    <!-- Detail modal -->
    <Teleport to="body">
      <div
        v-if="selectedAsset"
        class="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4"
        @click.self="selectedAsset = null"
      >
        <div class="bg-white rounded-2xl shadow-2xl max-w-2xl w-full max-h-[90vh] overflow-y-auto">
          <!-- Modal header -->
          <div class="flex items-center justify-between px-6 py-4 border-b border-gray-200">
            <h3 class="font-semibold text-gray-800">素材详情</h3>
            <button @click="selectedAsset = null" class="text-gray-400 hover:text-gray-600 text-2xl leading-none">&times;</button>
          </div>

          <div class="p-6 flex gap-6">
            <!-- Image -->
            <div class="flex-shrink-0">
              <img
                :src="assetImageUrl(selectedAsset)"
                :alt="selectedAsset.prompt"
                class="w-40 rounded-lg border border-gray-200"
              />
              <a
                :href="assetImageUrl(selectedAsset)"
                :download="selectedAsset.id + '.png'"
                class="mt-2 flex items-center justify-center gap-1.5 w-full px-3 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium rounded-lg transition-colors"
              >
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/>
                </svg>
                下载
              </a>
            </div>

            <!-- Details -->
            <div class="flex-1 min-w-0 space-y-3 text-sm">
              <div>
                <p class="text-xs text-gray-500 font-medium uppercase tracking-wide mb-1">Asset ID</p>
                <p class="font-mono text-gray-700 text-xs bg-gray-50 px-2 py-1 rounded">{{ selectedAsset.id }}</p>
              </div>
              <div>
                <p class="text-xs text-gray-500 font-medium uppercase tracking-wide mb-1">来源</p>
                <span class="text-xs px-2 py-0.5 rounded font-medium" :class="sourceClass(selectedAsset.source)">{{ selectedAsset.source }}</span>
              </div>
              <div>
                <p class="text-xs text-gray-500 font-medium uppercase tracking-wide mb-1">尺寸</p>
                <p class="text-gray-700">{{ selectedAsset.size || '未知' }}</p>
              </div>
              <div>
                <p class="text-xs text-gray-500 font-medium uppercase tracking-wide mb-1">创建日期</p>
                <p class="text-gray-700">{{ selectedAsset.created_at }}</p>
              </div>
              <div v-if="selectedAsset.used_in && selectedAsset.used_in.length">
                <p class="text-xs text-gray-500 font-medium uppercase tracking-wide mb-1">使用日期</p>
                <div class="flex flex-wrap gap-1">
                  <span v-for="d in selectedAsset.used_in" :key="d" class="text-xs bg-blue-50 text-blue-600 px-2 py-0.5 rounded">{{ d }}</span>
                </div>
              </div>
              <div v-if="selectedAsset.prompt">
                <p class="text-xs text-gray-500 font-medium uppercase tracking-wide mb-1">Prompt</p>
                <p class="text-gray-700 text-xs leading-relaxed bg-gray-50 p-3 rounded-lg">{{ selectedAsset.prompt }}</p>
              </div>
              <div v-if="selectedAsset.tags && selectedAsset.tags.length">
                <p class="text-xs text-gray-500 font-medium uppercase tracking-wide mb-1">标签</p>
                <div class="flex flex-wrap gap-1">
                  <span v-for="tag in selectedAsset.tags" :key="tag" class="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded">{{ tag }}</span>
                </div>
              </div>
              <div>
                <p class="text-xs text-gray-500 font-medium uppercase tracking-wide mb-1">备注</p>
                <textarea
                  v-model="noteDraft"
                  rows="3"
                  class="w-full text-sm border border-gray-200 rounded-lg px-2 py-1.5 text-gray-800"
                  placeholder="用途、场景、是否可作首图等"
                />
              </div>
              <div class="flex flex-wrap gap-2 pt-2">
                <button
                  type="button"
                  :disabled="noteSaving"
                  class="px-3 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-sm rounded-lg"
                  @click="saveNote"
                >
                  {{ noteSaving ? '保存中…' : '保存备注' }}
                </button>
                <button
                  type="button"
                  :disabled="deleting"
                  class="px-3 py-2 bg-red-600 hover:bg-red-700 disabled:opacity-50 text-white text-sm rounded-lg"
                  @click="removeAsset"
                >
                  {{ deleting ? '删除中…' : '从素材库删除' }}
                </button>
              </div>
              <p v-if="modalMsg" class="text-xs" :class="modalErr ? 'text-red-600' : 'text-green-600'">{{ modalMsg }}</p>
            </div>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { useRoute } from 'vue-router'
import { deleteAsset, getAssets, imageUrl, patchAssetNote } from '../api/index.js'

const route = useRoute()
const product = computed(() => decodeURIComponent(route.params.product || ''))

const assetsData = ref(null)
const loading = ref(true)
const loadError = ref(null)
const filterSource = ref('全部')
const searchQuery = ref('')
const selectedAsset = ref(null)
const noteDraft = ref('')
const noteSaving = ref(false)
const deleting = ref(false)
const modalMsg = ref('')
const modalErr = ref(false)

const allAssets = computed(() => assetsData.value?.assets || [])

const filteredAssets = computed(() => {
  let list = allAssets.value.filter(a => !a.disabled)
  if (filterSource.value !== '全部') {
    list = list.filter(a => a.source === filterSource.value)
  }
  if (searchQuery.value.trim()) {
    const q = searchQuery.value.toLowerCase()
    list = list.filter(a =>
      (a.prompt || '').toLowerCase().includes(q) ||
      (a.id || '').toLowerCase().includes(q) ||
      (a.tags || []).some(t => t.toLowerCase().includes(q))
    )
  }
  return list
})

function assetImageUrl(asset) {
  if (!asset.file) return ''
  // asset.file is relative to asset_library folder e.g. "images/abc.png"
  const assetLibraryPath = `campaigns/${product.value}/asset_library/${asset.file}`
  return imageUrl(assetLibraryPath)
}

function sourceClass(source) {
  switch (source) {
    case 'generate': return 'bg-violet-100 text-violet-700'
    case 'screenshot': return 'bg-amber-100 text-amber-700'
    case 'reuse': return 'bg-blue-100 text-blue-700'
    case 'user_upload': return 'bg-emerald-100 text-emerald-800'
    default: return 'bg-gray-100 text-gray-600'
  }
}

async function load() {
  loading.value = true
  loadError.value = null
  try {
    assetsData.value = await getAssets(product.value)
  } catch (e) {
    loadError.value = '无法加载素材库：' + e.message
  } finally {
    loading.value = false
  }
}

watch(selectedAsset, (a) => {
  noteDraft.value = a?.note || ''
  modalMsg.value = ''
  modalErr.value = false
})

async function saveNote() {
  if (!selectedAsset.value) return
  noteSaving.value = true
  modalMsg.value = ''
  modalErr.value = false
  try {
    await patchAssetNote(product.value, selectedAsset.value.id, noteDraft.value)
    modalMsg.value = '备注已保存'
    await load()
    const id = selectedAsset.value.id
    const next = (assetsData.value?.assets || []).find(x => x.id === id)
    selectedAsset.value = next || null
  } catch (e) {
    modalErr.value = true
    modalMsg.value = e.message || '保存失败'
  } finally {
    noteSaving.value = false
  }
}

async function removeAsset() {
  if (!selectedAsset.value) return
  if (!confirm('确定从素材库删除该素材？（软删除，流水线将不再使用）')) return
  deleting.value = true
  modalMsg.value = ''
  modalErr.value = false
  try {
    await deleteAsset(product.value, selectedAsset.value.id)
    selectedAsset.value = null
    await load()
  } catch (e) {
    modalErr.value = true
    modalMsg.value = e.message || '删除失败'
  } finally {
    deleting.value = false
  }
}

async function removeAssetById(assetId) {
  if (!assetId) return
  if (!confirm('确定从素材库删除该素材？（软删除，流水线将不再使用）')) return
  deleting.value = true
  try {
    await deleteAsset(product.value, assetId)
    if (selectedAsset.value?.id === assetId) {
      selectedAsset.value = null
    }
    await load()
  } catch (e) {
    loadError.value = '删除失败：' + (e.message || '未知错误')
  } finally {
    deleting.value = false
  }
}

watch(product, load, { immediate: true })
</script>
