import { createRouter, createWebHashHistory } from 'vue-router'

import Overview from '../views/Overview.vue'
import PostDetail from '../views/PostDetail.vue'
import AuditReport from '../views/AuditReport.vue'
import PipelineLog from '../views/PipelineLog.vue'
import AssetLibrary from '../views/AssetLibrary.vue'
import LessonMemory from '../views/LessonMemory.vue'
import ProductSettings from '../views/ProductSettings.vue'

const routes = [
  // Both '/' and '/products' are placeholders; Sidebar auto-navigates to first product/date on load
  { path: '/', component: Overview, props: () => ({ product: '', date: '' }) },
  { path: '/products', component: Overview, props: () => ({ product: '', date: '' }) },
  // Must be before /:product/:date so "settings" is not parsed as a date
  { path: '/:product/settings', name: 'ProductSettings', component: ProductSettings },
  { path: '/:product/:date', component: Overview },
  { path: '/:product/:date/post', component: PostDetail },
  { path: '/:product/:date/audit', component: AuditReport },
  { path: '/:product/:date/log', component: PipelineLog },
  { path: '/:product/assets', component: AssetLibrary },
  { path: '/:product/memory', component: LessonMemory },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

export default router
