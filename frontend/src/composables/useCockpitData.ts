import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import client from '../api/client'
import type { HistoryResponse } from '../api/monitorTypes'
import { loadSystemSettings, systemSettings } from '../stores/systemSettings'

export interface WallMonitor { id:string;name:string;business:string;type:string;status:string;available:boolean|null;latency_ms:number|null;last_checked_at:string|null }
export interface WallSnapshot { snapshot_at:string;businesses_total:number;monitors_total:number;states:Record<string,number>;health_rate:number|null;open_incidents:number;probe_stats_24h:{total:number;passed:number;failed:number;success_rate:number|null;average_latency_ms:number|null};recent_incidents:Array<{id:string;title:string;severity:string;business:string;opened_at:string}>;latest_monitors:WallMonitor[] }
export interface WallSla { monitor_id:string;monitor_name:string;business_name:string;availability:number|null;samples:number }
export function useCockpitData() {
 const snapshot=ref<WallSnapshot|null>(null), history=ref<HistoryResponse|null>(null), sla=ref<WallSla[]>([]),slaUnavailable=ref(false),periodHours=ref(12),loading=ref(false),error=ref('')
 let controller:AbortController|undefined,version=0,stopped=false,timer:ReturnType<typeof setInterval>|undefined
 const monitors=computed(()=>snapshot.value?.latest_monitors||[])
 const monitorMap=computed(()=>Object.fromEntries(monitors.value.map(item=>[item.id,item])))
 const latest=computed(()=>history.value?.series.slice(-10).reverse()||[])
 const slowest=computed(()=>{
  const top:HistoryResponse['series']=[]
  for(const point of history.value?.series||[])if(point.latency_ms!=null){top.push(point);top.sort((a,b)=>Number(b.latency_ms)-Number(a.latency_ms));if(top.length>5)top.pop()}
  return top
 })
 async function load(force=false){
  if(stopped||loading.value&&!force)return
  controller?.abort();controller=new AbortController();const current=++version
  const before=new Date(),after=new Date(before.getTime()-periodHours.value*3600000)
  loading.value=true
  try{
   const request={signal:controller.signal}
   const [summary,points,report]=await Promise.all([
    client.get<WallSnapshot>('/dashboard/summary/',request),
    client.get<HistoryResponse>('/monitors/history/',{...request,params:{checked_after:after.toISOString(),checked_before:before.toISOString(),page_size:1},timeout:60000}),
    client.get('/reports/sla/',{...request,params:{days:1}}).then(response=>({rows:response.data.results||[],unavailable:false})).catch(()=>({rows:[],unavailable:true})),
   ])
   if(stopped||current!==version)return
   snapshot.value=summary.data;history.value=points.data;sla.value=report.rows;slaUnavailable.value=report.unavailable;error.value=''
  }catch(err:any){if(!stopped&&current===version&&err.code!=='ERR_CANCELED')error.value='同步异常，当前显示上次成功快照；请检查数据连接。'}
  finally{if(current===version)loading.value=false}
 }
 watch(periodHours,()=>{history.value=null;load(true)})
 onMounted(async()=>{
  load()
  try{await loadSystemSettings()}catch{/* Keep the documented 10-second fallback. */}
  if(!stopped)timer=setInterval(()=>load(),Math.max(5,Number(systemSettings.monitor_wall_refresh_seconds)||10)*1000)
 })
 onBeforeUnmount(()=>{stopped=true;version++;controller?.abort();if(timer)clearInterval(timer)})
 return{snapshot,history,sla,slaUnavailable,periodHours,loading,error,monitors,monitorMap,latest,slowest,load}
}
