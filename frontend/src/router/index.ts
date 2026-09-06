import { createRouter, createWebHistory } from 'vue-router'
import DashboardView from '../views/DashboardView.vue'
import LayoutView from '../views/LayoutView.vue'
import LoginView from '../views/LoginView.vue'
import PublicStatusView from '../views/PublicStatusView.vue'
import ResourceView from '../views/ResourceView.vue'
import { resourceConfigs } from '../config/resources'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', component: LoginView },
    { path: '/status/:slug', component: PublicStatusView },
    { path: '/', component: LayoutView, children: [
      { path: '', component: DashboardView },
      { path: 'monitor-wall', component: () => import('../views/MonitorWallView.vue') },
      ...Object.entries(resourceConfigs).filter(([path]) => !['users','departments','roles','monitor-results','channels','incidents','rules','notifications','audit','maintenance','status-pages'].includes(path)).map(([path, config]) => ({ path, component: ResourceView, props: { config } })),
      { path: 'incidents', component: () => import('../views/IncidentsView.vue') },
      { path: 'rules', component: () => import('../views/AlertRulesView.vue') },
      { path: 'notifications', component: () => import('../views/NotificationLogsView.vue') },
      { path: 'monitor-results', component: () => import('../views/MonitorResultsView.vue') },
      { path: 'channels', component: () => import('../views/NotificationChannelsView.vue') },
      { path: 'users', component: () => import('../views/UserManagementView.vue') },
      { path: 'departments', component: () => import('../views/DepartmentManagementView.vue') },
      { path: 'roles', component: () => import('../views/RoleManagementView.vue') },
      { path: 'sla', component: () => import('../views/SlaView.vue') },
      { path: 'maintenance', component: () => import('../views/MaintenanceWindowsView.vue') },
      { path: 'status-pages', component: () => import('../views/StatusPagesManagementView.vue') },
      { path: 'system-health', component: () => import('../views/SystemHealthView.vue') },
      { path: 'system-settings', component: () => import('../views/SystemSettingsView.vue') },
      { path: 'audit', component: () => import('../views/AuditLogsView.vue') },
      { path: 'login-records', component: () => import('../views/LoginRecordsView.vue') },
    ] },
  ],
})
router.beforeEach((to) => {
  if (to.path !== '/login' && !to.path.startsWith('/status/') && !localStorage.getItem('access_token')) return '/login'
})
export default router
