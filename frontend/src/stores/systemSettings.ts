import { reactive } from 'vue'
import client from '../api/client'

export const systemSettings = reactive({
  brand_logo_text: '合力数据',
  home_page_title: '合力数据业务监控系统',
  browser_title: '合力数据业务监控系统',
  login_page_description: '企业级业务可用性监控与告警平台',
  monitor_wall_title: '合力数据业务监控系统',
  dashboard_refresh_seconds: 30,
  monitor_wall_refresh_seconds: 10,
  monitor_result_retention_count: 10000,
  can_manage: false,
})

export async function loadSystemSettings() {
  const { data } = await client.get('/system/settings/')
  Object.assign(systemSettings, data)
  document.title = systemSettings.browser_title
  return systemSettings
}
