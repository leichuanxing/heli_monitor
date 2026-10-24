import { computed, onMounted, ref } from 'vue'
import client from '../api/client'
export function useIamManage() {
 const account=ref<{id?:number;is_superuser?:boolean;permissions:string[]}>({permissions:[]})
 const canManage=computed(()=>!!account.value.is_superuser||account.value.permissions.includes('iam.manage'))
 onMounted(async()=>{try{account.value=(await client.get('/auth/me/')).data}catch{account.value={permissions:[]}}})
 return {account,canManage}
}
