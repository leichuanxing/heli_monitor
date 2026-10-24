import { onMounted, ref } from 'vue'
import client from '../api/client'
export function useReportManage() {
  const canManage = ref(false)
  onMounted(async () => {
    try { const {data} = await client.get('/auth/me/'); canManage.value = !!data.is_superuser || (data.permissions || []).includes('report.manage') }
    catch { canManage.value = false }
  })
  return canManage
}
