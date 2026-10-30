<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import * as echarts from 'echarts/core'
import { ScatterChart, LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent, DataZoomComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
echarts.use([ScatterChart,LineChart,GridComponent,TooltipComponent,LegendComponent,DataZoomComponent,CanvasRenderer])
import client from '../api/client'
import { certificateExpiry } from '../components/certificateHistory'
import { chartAppearance } from '../composables/chartAppearance'
import { theme } from '../stores/theme'
import type { HistoryResponse, MonitorResult } from '../api/monitorTypes'

const props=defineProps<{monitorId?:string}>()
const route=useRoute(),router=useRouter(),standalone=computed(()=>Boolean(props.monitorId||route.params.monitorId)),monitor=ref(String(props.monitorId||route.params.monitorId||route.query.monitor||'')),kind=ref(''),success=ref(''),search=ref('')
const monitors=ref<Array<{id:string;name:string;is_archived:boolean;monitor_type:string;certificate?:{expires_at:string|null;days_remaining:number|null;warning:boolean;stale:boolean;checked_at:string}|null}>>([]),loading=ref(false),page=ref(1),pageSize=ref(20)
const data=ref<HistoryResponse|null>(null),range=ref<[Date,Date]>([new Date(Date.now()-86400000),new Date()]),quick=ref(24)
const availabilityElement=ref<HTMLElement>(),chartElement=ref<HTMLElement>(),detail=ref<MonitorResult|null>(null),detailVisible=ref(false)
let availabilityChart:echarts.EChartsType|undefined,chart:echarts.EChartsType|undefined,observer:ResizeObserver|undefined,version=0,disposed=false
const certificateTasks=computed(()=>monitors.value.filter(m=>standalone.value&&m.monitor_type==='SSL'&&(!monitor.value||m.id===monitor.value)&&(!kind.value||kind.value==='SSL')))
const showCertificate=computed(()=>kind.value==='SSL'||data.value?.results.some(row=>row.monitor_type==='SSL'))
const types=['HTTP','API','TCP','PING','DNS','SSL','MSSQL','POSTGRESQL','MYSQL','MONGODB']
const title=computed(()=>monitor.value?`${monitors.value.find(m=>m.id===monitor.value)?.name||'当前任务'} · 历史数据`:'全部探测任务 · 历史数据')
const escapeHtml=(value:string)=>value.replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]||char))
const fmt=(value:string|null)=>value?new Date(value).toLocaleString():'—'
const number=(value:number|null|undefined)=>value==null?'—':Number(value).toFixed(2)
const disabledDate=(date:Date)=>date.getTime()>Date.now()||date.getTime()<Date.now()-31*86400000
function chooseRange(hours:number){quick.value=hours;range.value=[new Date(Date.now()-hours*3600000),new Date()];page.value=1;load()}
function changed(){quick.value=0;page.value=1;load()}
function filterChanged(){page.value=1;load()}
function validRange(){
 if(!range.value?.[0]||!range.value?.[1]){ElMessage.warning('请选择起止时间');return false}
 const [start,end]=range.value.map(x=>x.getTime())
 if(end<=start||end-start>30*86400000+1000||end>Date.now()+60000){ElMessage.warning('时间范围必须大于零、最长 30 天且不能晚于当前时间');return false}
 return true
}
function render(){
 if(!chartElement.value||!data.value||disposed)return
 chart ||= echarts.init(chartElement.value)
 const appearance=chartAppearance()
 const grouped=new Map<string,HistoryResponse['series']>()
 for(const point of data.value.series){const points=grouped.get(point.monitor)||[];points.push(point);grouped.set(point.monitor,points)}
 const groups=[...grouped.entries()]
 const taskName=(id:string)=>monitors.value.find(m=>m.id===id)?.name||'任务 '+id.slice(0,8)
 const xAxis={type:'time',min:new Date(data.value.checked_after).getTime(),max:new Date(data.value.checked_before).getTime(),axisLabel:{...appearance.xAxis.axisLabel,hideOverlap:true}}
 const dataZoom=[{type:'inside',filterMode:'none'},{type:'slider',height:20,bottom:8,filterMode:'none',borderColor:'transparent',fillerColor:theme.value==='dark'?'#76a5ff22':'#2867dc14',textStyle:appearance.textStyle,handleStyle:{color:appearance.color[0]},dataBackground:{lineStyle:{color:appearance.color[0],opacity:0.3},areaStyle:{opacity:0.05}}}]
 const legend={type:'scroll',top:0,bottom:'auto',data:groups.map(([id])=>taskName(id))}
 chart.setOption({...appearance,tooltip:{...appearance.tooltip,trigger:'axis'},legend:{...legend,textStyle:appearance.textStyle},grid:{left:55,right:25,bottom:65,top:45},xAxis:{...appearance.xAxis,...xAxis},
  yAxis:{...appearance.yAxis,type:'value',name:'实际响应(ms)'},dataZoom,
  series:groups.map(([id,points])=>({name:taskName(id),type:'line',smooth:0.6,encode:{x:0,y:1,tooltip:[1]},showSymbol:false,symbolSize:4,connectNulls:false,
   data:points.map(x=>[new Date(x.at).getTime(),x.latency_ms,x.id]),lineStyle:{width:2},emphasis:{focus:'series'}}))},true)
 if(availabilityElement.value){
  availabilityChart ||= echarts.init(availabilityElement.value)
  availabilityChart.setOption({...appearance,tooltip:{...appearance.tooltip,trigger:'item',formatter:(p:any)=>`${escapeHtml(String(p.seriesName))}<br/>${new Date(p.value[0]).toLocaleString()}<br/>${p.value[1]?'成功':'失败'} · 记录 #${p.value[2]}`},legend:{...legend,textStyle:appearance.textStyle},grid:{left:55,right:25,bottom:65,top:45},xAxis:{...appearance.xAxis,...xAxis},dataZoom,
   yAxis:{...appearance.yAxis,type:'value',min:0,max:1,interval:1,axisLabel:{...appearance.yAxis.axisLabel,formatter:(value:number)=>value===1?'成功':'失败'}},
   series:groups.map(([id,points])=>({name:taskName(id),type:'scatter',symbolSize:5,progressive:5000,
    data:points.map(x=>[new Date(x.at).getTime(),x.success?1:0,x.id]),
    itemStyle:{color:(p:any)=>p.value[1]?'#38a378':'#db5b64'}}))},true)
 }

}
async function load(){
 if(!validRange())return
 const current=++version;loading.value=true
 try{const response=await client.get<HistoryResponse>('/monitors/history/',{params:{monitor:monitor.value||undefined,monitor_type:kind.value||undefined,
  success:success.value||undefined,search:search.value||undefined,checked_after:range.value[0].toISOString(),checked_before:range.value[1].toISOString(),page:page.value,page_size:pageSize.value}})
  if(disposed||current!==version)return
  data.value=response.data;await nextTick();render()
 }catch(e:any){if(current===version)ElMessage.error(e.response?.data?.details?JSON.stringify(e.response.data.details):'历史数据加载失败')}
 finally{if(current===version)loading.value=false}
}
async function options(){
 const result:typeof monitors.value=[]
 let current=1,hasNext=true
 while(hasNext&&!disposed){const{data}=await client.get('/monitors/',{params:{page_size:500,page:current}});result.push(...(data.results||data));hasNext=Boolean(data.next);current++}
 if(!disposed){monitors.value=result;render()}
}
function showDetail(row:MonitorResult){detail.value=row;detailVisible.value=true}
async function refreshHistory(){await Promise.all([load(),options().catch(()=>ElMessage.error('证书标签刷新失败'))])}
watch(theme,()=>{const appearance=chartAppearance();for(const instance of [chart,availabilityChart])instance?.setOption({...appearance,legend:{textStyle:appearance.textStyle}})})
watch(()=>props.monitorId||route.params.monitorId||route.query.monitor,value=>{monitor.value=String(value||'');filterChanged()})
onMounted(async()=>{load();options().catch(()=>ElMessage.error('任务选项加载失败'));await nextTick();if(chartElement.value){observer=new ResizeObserver(()=>{chart?.resize();availabilityChart?.resize()});observer.observe(chartElement.value);if(availabilityElement.value)observer.observe(availabilityElement.value)}})
onBeforeUnmount(()=>{disposed=true;version++;observer?.disconnect();chart?.dispose();availabilityChart?.dispose()})
</script>
<template>
 <div class="history-heading"><div><h2>{{standalone?'任务历史数据':'历史趋势'}}</h2><p>{{title}}</p></div><div><el-button v-if="standalone&&!props.monitorId" @click="router.push('/monitors')">返回探测任务</el-button><el-button :loading="loading" @click="refreshHistory">刷新当前范围</el-button></div></div>
 <el-card shadow="never" class="history-filters">
  <div v-if="!standalone" class="filter-row"><el-select v-model="monitor" filterable clearable placeholder="全部探测任务" @change="filterChanged"><el-option v-for="m in monitors" :key="m.id" :label="m.name" :value="m.id"/></el-select>
   <el-select v-model="kind" clearable placeholder="全部类型" @change="filterChanged"><el-option v-for="type in types" :key="type" :value="type"/></el-select>
   <el-select v-model="success" clearable placeholder="全部结果" @change="filterChanged"><el-option label="成功" value="true"/><el-option label="失败" value="false"/></el-select>
   <el-input v-model="search" clearable placeholder="搜索任务、业务或目标" @clear="filterChanged" @keyup.enter="filterChanged"/><el-button @click="filterChanged">查询</el-button>
  </div>
  <div class="filter-row"><el-radio-group :model-value="quick" @change="chooseRange(Number($event))"><el-radio-button :value="1">近 1 小时</el-radio-button><el-radio-button :value="6">近 6 小时</el-radio-button><el-radio-button :value="24">近 24 小时</el-radio-button><el-radio-button :value="168">近 7 天</el-radio-button><el-radio-button :value="720">近 1 个月</el-radio-button></el-radio-group>
   <el-date-picker v-model="range" type="datetimerange" start-placeholder="开始时间" end-placeholder="结束时间" :disabled-date="disabledDate" :clearable="false" @change="changed"/><small>自定义时间范围最长 30 天</small>
  </div>
 </el-card>
 <div class="history-summary" :style="{'--summary-columns':5+certificateTasks.length}"><div><span>探测总次数</span><b>{{data?.summary.total??0}}</b></div><div><span>成功率</span><b>{{data?.summary.availability==null?'—':data.summary.availability+'%'}}</b></div><div><span>失败次数</span><b>{{data?.summary.failed??0}}</b></div><div><span>平均响应</span><b>{{number(data?.summary.average_latency_ms)}} <small>ms</small></b></div><div><span>最大响应</span><b>{{number(data?.summary.max_latency_ms)}} <small>ms</small></b></div><div v-for="task in certificateTasks" :key="task.id" class="certificate-summary" :title="task.certificate?.checked_at?'最近探测于 '+fmt(task.certificate.checked_at):'尚未获取证书信息'"><span>证书有效期<template v-if="certificateTasks.length>1"> · {{task.name}}</template></span><b class="certificate-days">{{task.certificate?.days_remaining==null?'未获取':task.certificate.days_remaining<0?'已过期 '+Math.abs(task.certificate.days_remaining)+' 天':task.certificate.days_remaining+' 天'}}</b><small v-if="task.certificate?.expires_at">到期：{{fmt(task.certificate.expires_at)}}</small><el-tag v-if="task.certificate?.stale" size="small" type="warning">数据已过期</el-tag><el-tag v-else-if="task.certificate?.warning" size="small" type="warning">到期预警</el-tag></div></div>
 <el-alert :title="data?.note||'正在加载历史数据'" :description="`当前范围实际记录：${fmt(data?.summary.first_checked_at||null)} 至 ${fmt(data?.summary.last_checked_at||null)}`" type="info" :closable="false"/>
 <el-card shadow="never" class="history-chart"><div class="chart-heading"><b>响应时间趋势</b><small>逐次原始数据 · 共 {{data?.series.length||0}} 个时间点 · 可拖动缩放</small></div><div ref="chartElement" v-loading="loading" style="height:310px"/><el-empty v-if="data&&!data.count" description="此范围暂无历史数据" :image-size="60"/></el-card>
 <el-card shadow="never" class="history-chart"><div class="chart-heading"><b>逐次探测结果</b><small>每个点对应一次实际探测 · 绿色成功 / 红色失败</small></div><div ref="availabilityElement" v-loading="loading" style="height:280px"/></el-card>
 <el-card shadow="never" class="history-table"><el-table v-loading="loading" :data="data?.results||[]" stripe empty-text="此范围暂无探测记录"><el-table-column prop="checked_at" label="探测时间" min-width="180"><template #default="s">{{fmt(s.row.checked_at)}}</template></el-table-column><el-table-column prop="monitor_name" label="任务" min-width="180" show-overflow-tooltip/><el-table-column prop="business_name" label="业务" min-width="140" show-overflow-tooltip/><el-table-column prop="monitor_type" label="类型" width="120"/><el-table-column label="结果" width="90"><template #default="s"><el-tag :type="s.row.success?'success':'danger'">{{s.row.success?'成功':'失败'}}</el-tag></template></el-table-column><el-table-column label="响应(ms)" width="120"><template #default="s">{{number(s.row.latency_ms)}}</template></el-table-column><el-table-column v-if="showCertificate" label="证书到期时间" min-width="190"><template #default="s"><span v-if="s.row.monitor_type==='SSL'">{{certificateExpiry(s.row)?fmt(certificateExpiry(s.row)):'未获取'}}</span><span v-else>—</span></template></el-table-column><el-table-column v-if="showCertificate" label="探测时剩余有效期" min-width="155"><template #default="s"><template v-if="s.row.monitor_type==='SSL'"><span>{{s.row.ssl_days_remaining==null?'未获取':s.row.ssl_days_remaining+' 天'}}</span><el-tag v-if="s.row.metrics?.warning" size="small" type="warning">到期预警</el-tag></template><span v-else>—</span></template></el-table-column><el-table-column prop="error_summary" label="失败原因" min-width="180" show-overflow-tooltip/><el-table-column label="操作" width="80" fixed="right"><template #default="s"><el-button link type="primary" @click="showDetail(s.row)">详情</el-button></template></el-table-column></el-table>
  <el-pagination v-model:current-page="page" v-model:page-size="pageSize" :total="data?.count||0" :page-sizes="[20,50,100]" layout="total,sizes,prev,pager,next" @current-change="load" @size-change="filterChanged"/>
 </el-card>
 <el-dialog v-model="detailVisible" title="历史探测详情" width="760px"><template v-if="detail"><el-descriptions :column="2" border><el-descriptions-item label="任务">{{detail.monitor_name}}</el-descriptions-item><el-descriptions-item label="时间">{{fmt(detail.checked_at)}}</el-descriptions-item><el-descriptions-item label="目标" :span="2">{{detail.monitor_target}}</el-descriptions-item><el-descriptions-item label="状态码">{{detail.status_code??'—'}}</el-descriptions-item><el-descriptions-item v-if="detail.monitor_type==='SSL'" label="证书到期时间">{{certificateExpiry(detail)?fmt(certificateExpiry(detail)):'未获取'}}</el-descriptions-item><el-descriptions-item v-if="detail.monitor_type==='SSL'" label="探测时剩余有效期">{{detail.ssl_days_remaining==null?'未获取':detail.ssl_days_remaining+' 天'}}</el-descriptions-item><el-descriptions-item label="丢包率">{{detail.packet_loss??'—'}}%</el-descriptions-item><el-descriptions-item label="响应耗时">{{number(detail.latency_ms)}} ms</el-descriptions-item></el-descriptions><h4>断言与指标</h4><pre>{{JSON.stringify({assertions:detail.assertions,metrics:detail.metrics,detail:detail.detail},null,2)}}</pre></template></el-dialog>
</template>
<style scoped>
.history-heading{display:flex;justify-content:space-between;align-items:center;margin-bottom:16px}.history-heading h2{margin:0}.history-heading p{margin:6px 0 0;color:var(--muted)}.filter-row{display:flex;gap:10px;align-items:center;flex-wrap:wrap}.filter-row+.filter-row{margin-top:14px}.filter-row .el-select{width:190px}.filter-row .el-input{width:220px}.filter-row small{color:var(--muted)}.history-summary{display:grid;grid-template-columns:repeat(var(--summary-columns,5),minmax(0,1fr));gap:12px;margin:16px 0}.history-summary>div{padding:16px;background:var(--surface);border:1px solid var(--border);border-top:3px solid #347fd3;border-radius:6px}.history-summary span{display:block;color:var(--muted);font-size:12px}.history-summary b{display:block;font-size:23px;margin-top:8px}.history-summary small{font-size:12px}.history-summary .certificate-summary{min-width:0}.history-summary .certificate-days{font-size:23px;line-height:1.45;overflow-wrap:anywhere}.certificate-summary>small{display:block;color:var(--muted);margin-top:6px}.certificate-summary :deep(.el-tag){margin-top:6px}.history-chart,.history-table{margin-top:16px}.chart-heading{display:flex;justify-content:space-between}.chart-heading small{color:var(--muted)}.el-pagination{margin-top:16px;justify-content:flex-end}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:var(--surface-subtle);padding:14px;max-height:350px;overflow:auto}@media(max-width:900px){.history-summary{grid-template-columns:repeat(2,1fr)}}
</style>
