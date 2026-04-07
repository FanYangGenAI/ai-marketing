<template>
  <div class="flex border-b border-gray-200 bg-white">
    <router-link
      v-for="tab in tabs"
      :key="tab.to"
      :to="tab.to"
      exact-active-class=""
      class="px-5 py-3 text-sm font-medium transition-colors border-b-2 -mb-px whitespace-nowrap"
      :class="isActive(tab) ? 'border-blue-600 text-blue-600' : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'"
    >
      {{ tab.label }}
    </router-link>
  </div>
</template>

<script setup>
import { useRoute } from 'vue-router'

const props = defineProps({
  product: String,
  date: String,
})

const route = useRoute()

const tabs = [
  { label: '总览', suffix: '' },
  { label: '帖子预览', suffix: '/post' },
  { label: '审核报告', suffix: '/audit' },
  { label: '流水线日志', suffix: '/log' },
].map(t => ({
  label: t.label,
  to: `/${encodeURIComponent(props.product)}/${props.date}${t.suffix}`,
  suffix: t.suffix,
}))

function isActive(tab) {
  const base = `/${encodeURIComponent(props.product)}/${props.date}`
  const currentPath = route.path
  if (tab.suffix === '') {
    // Overview: active only when exactly at /:product/:date
    return currentPath === base
  }
  return currentPath === base + tab.suffix
}
</script>
