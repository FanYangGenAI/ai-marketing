<template>
  <div class="relative w-full" style="aspect-ratio: 3/4; background: #f3f4f6;">
    <!-- Current image -->
    <img
      v-if="images.length > 0"
      :src="currentImageUrl"
      :alt="currentImage.caption || ''"
      class="w-full h-full object-cover cursor-pointer select-none"
      @click="$emit('open-lightbox', currentIndex)"
    />
    <div v-else class="w-full h-full flex items-center justify-center text-gray-400 text-sm">
      暂无图片
    </div>

    <!-- Navigation arrows -->
    <template v-if="images.length > 1">
      <button
        @click.stop="prev"
        class="absolute left-2 top-1/2 -translate-y-1/2 w-8 h-8 bg-black/40 hover:bg-black/60 text-white rounded-full flex items-center justify-center transition-colors"
        aria-label="上一张"
      >
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M15 19l-7-7 7-7"/>
        </svg>
      </button>
      <button
        @click.stop="next"
        class="absolute right-2 top-1/2 -translate-y-1/2 w-8 h-8 bg-black/40 hover:bg-black/60 text-white rounded-full flex items-center justify-center transition-colors"
        aria-label="下一张"
      >
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M9 5l7 7-7 7"/>
        </svg>
      </button>
    </template>

    <!-- Dot indicators -->
    <div
      v-if="images.length > 1"
      class="absolute bottom-3 left-1/2 -translate-x-1/2 flex gap-1.5"
    >
      <button
        v-for="(_, i) in images"
        :key="i"
        @click.stop="currentIndex = i"
        class="w-1.5 h-1.5 rounded-full transition-colors"
        :class="i === currentIndex ? 'bg-white' : 'bg-white/50'"
        :aria-label="`第${i+1}张`"
      />
    </div>

    <!-- Image counter -->
    <div
      v-if="images.length > 1"
      class="absolute top-2 right-2 bg-black/50 text-white text-xs px-2 py-0.5 rounded-full"
    >
      {{ currentIndex + 1 }}/{{ images.length }}
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { imageUrl } from '../api/index.js'

const props = defineProps({
  images: {
    type: Array,
    default: () => []
  }
})

defineEmits(['open-lightbox'])

const currentIndex = ref(0)

const currentImage = computed(() => props.images[currentIndex.value] || {})
const currentImageUrl = computed(() => imageUrl(currentImage.value.path))

function prev() {
  currentIndex.value = (currentIndex.value - 1 + props.images.length) % props.images.length
}

function next() {
  currentIndex.value = (currentIndex.value + 1) % props.images.length
}

// Expose for parent to control
defineExpose({ currentIndex })
</script>
