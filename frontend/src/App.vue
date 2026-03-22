<template>
  <div class="flex h-screen overflow-hidden bg-gray-50">
    <!-- Left sidebar -->
    <Sidebar class="flex-shrink-0" />

    <!-- Right main content area -->
    <main class="flex-1 overflow-y-auto bg-gray-50">
      <router-view />
    </main>
  </div>
</template>

<script setup>
import Sidebar from './components/Sidebar.vue'
</script>
