<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { ElMessage } from 'element-plus'
import * as echarts from 'echarts/core'
import { LineChart, PieChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import WallPanel from '../components/WallPanel.vue'
import { fitWall } from '../components/wallFit'
import { useCockpitData } from '../composables/useCockpitData'
import { chartAppearance } from '../composables/chartAppearance'
import { systemSettings } from '../stores/systemSettings'

echarts.use([LineChart,PieChart,GridComponent,LegendComponent,TooltipComponent,CanvasRenderer])
const {snapshot,history,sla,slaUnavailable,periodHours,loading,error,monitors,monitorMap,latest,slowest,load}=useCockpitData()
const host=ref<HTMLElement>(),trendEl=ref<HTMLElement>(),typeEl=ref<HTMLElement>(),now=ref(new Date()),autoRotate=ref(true),fullscreen=ref(false),motionEnabled=ref(true)
const geometry=reactive({scale:1,left:0,top:0,width:1920,height:1080,canvasWidth:1920,canvasHeight:1080})
const pages=reactive({nodes:0,inventory:0,sla:0,events:0,stream:0})
const statuses=[['UP','正常'],['DOWN','故障'],['DEGRADED','降级'],['MAINTENANCE','维护'],['PAUSED','暂停'],['PENDING','待探测'],['UNKNOWN','未知']]
const color=(status:string)=>({UP:'#32d6a4',DOWN:'#ff7188',DEGRADED:'#ffbf69',MAINTENANCE:'#57bfff',PAUSED:'#7796ad',PENDING:'#9bafd0',UNKNOWN:'#8b9dac'}[status]||'#8b9dac')
const label=(status:string)=>statuses.find(item=>item[0]===status)?.[1]||status
const number=(value:number|null|undefined,digits=0)=>value==null?'—':Number(value).toLocaleString('zh-CN',{maximumFractionDigits:digits})
const time=(value:string|null|undefined)=>value?new Date(value).toLocaleTimeString('zh-CN',{hour12:false}):'—'
const range=(value:string)=>new Date(value).toLocaleString('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false})
const stats=computed(()=>snapshot.value?.probe_stats_24h)
const stale=computed(()=>!!snapshot.value&&now.value.getTime()-new Date(snapshot.value.snapshot_at).getTime()>Math.max(60,3*(systemSettings.monitor_wall_refresh_seconds||10))*1000)
const incidents=computed(()=>snapshot.value?.recent_incidents||[])
const kpis=computed(()=>[
 {label:'业务系统',value:number(snapshot.value?.businesses_total),unit:''},
 {label:'探测任务',value:number(snapshot.value?.monitors_total),unit:''},
 {label:'整体健康度',value:number(snapshot.value?.health_rate,1),unit:snapshot.value?.health_rate==null?'':'%',color:'#32d6a4'},
 {label:'24H 探测次数',value:number(stats.value?.total),unit:''},
 {label:'24H 成功率',value:number(stats.value?.success_rate,2),unit:stats.value?.success_rate==null?'':'%',color:'#32d6a4'},
 {label:'24H 失败次数',value:number(stats.value?.failed),unit:'',color:stats.value?.failed?'#ff7188':undefined},
 {label:'24H 平均响应',value:number(stats.value?.average_latency_ms,2),unit:stats.value?.average_latency_ms==null?'':'ms'},
 {label:'开放事件',value:number(snapshot.value?.open_incidents),unit:'',color:snapshot.value?.open_incidents?'#ff7188':undefined},
])
const pageItems=<T,>(items:T[],page:number,size:number)=>items.slice(Math.min(page,Math.max(0,Math.ceil(items.length/size)-1))*size,(Math.min(page,Math.max(0,Math.ceil(items.length/size)-1))+1)*size)
let trend:echarts.EChartsType|undefined,typeChart:echarts.EChartsType|undefined,observer:ResizeObserver|undefined,clock:ReturnType<typeof setInterval>|undefined,frame:number|undefined,lastRatio=0,disposed=false
function renderCharts(){
 if(disposed||!trendEl.value||!typeEl.value)return
 const ratio=Math.max(.5,Math.min(4,(window.devicePixelRatio||1)*geometry.scale))
 if(Math.abs(ratio-lastRatio)>.05){trend?.dispose();typeChart?.dispose();trend=undefined;typeChart=undefined;lastRatio=ratio}
 trend??=echarts.init(trendEl.value,undefined,{devicePixelRatio:ratio});typeChart??=echarts.init(typeEl.value,undefined,{devicePixelRatio:ratio})
 const appearance=chartAppearance('dark'),groups=new Map<string,Array<[number,number|null,number]>>()
 for(const point of history.value?.series||[]){const entries=groups.get(point.monitor)||[];entries.push([new Date(point.at).getTime(),point.latency_ms,point.id]);groups.set(point.monitor,entries)}
 trend.setOption({...appearance,animation:false,tooltip:{...appearance.tooltip,trigger:'axis',renderMode:'richText'},legend:{type:'scroll',top:0,textStyle:{color:'#a5c4dd',fontSize:11}},grid:{left:48,right:18,top:40,bottom:30},xAxis:{...appearance.xAxis,type:'time',min:history.value?new Date(history.value.checked_after).getTime():undefined,max:history.value?new Date(history.value.checked_before).getTime():undefined},yAxis:{...appearance.yAxis,type:'value',name:'ms'},series:[...groups.entries()].map(([id,points])=>({name:monitorMap.value[id]?.name||id.slice(0,8),type:'line',smooth:.4,showSymbol:false,connectNulls:false,encode:{x:0,y:1,tooltip:[1]},data:points,lineStyle:{width:2}}))},true)
 const counts:Record<string,number>={};for(const item of monitors.value)counts[item.type]=(counts[item.type]||0)+1
 typeChart.setOption({...appearance,animation:false,tooltip:{...appearance.tooltip,renderMode:'richText'},legend:{type:'scroll',bottom:0,textStyle:{color:'#9fc0da',fontSize:11},itemWidth:10,itemHeight:8},series:[{type:'pie',radius:['44%','72%'],center:['50%','42%'],label:{show:false},itemStyle:{borderColor:'#0b2034',borderWidth:3},data:Object.entries(counts).map(([name,value])=>({name,value}))}]},true)
 trend.resize();typeChart.resize()
}
function resize(){
 if(!host.value)return
 if(document.fullscreenElement!==host.value){
  const top=Math.max(0,host.value.getBoundingClientRect().top)
  const wrapper=host.value.closest('.content-wrap')
  const bottom=wrapper?parseFloat(getComputedStyle(wrapper).paddingBottom)||0:16
  host.value.style.setProperty('--wall-available-height',Math.max(260,window.innerHeight-top-bottom-2)+'px')
 }
 const width=host.value.clientWidth,height=host.value.clientHeight
 Object.assign(geometry,fitWall(width,height),{width,height})
 if(frame)cancelAnimationFrame(frame)
 frame=requestAnimationFrame(()=>{frame=undefined;renderCharts()})
}
async function toggleFull(){try{if(document.fullscreenElement===host.value)await document.exitFullscreen();else await host.value?.requestFullscreen()}catch{ElMessage.error('无法进入全屏，请允许浏览器全屏后重试')}}
function fullChanged(){fullscreen.value=document.fullscreenElement===host.value;nextTick(resize)}
watch([history,monitors],()=>nextTick(renderCharts))
onMounted(()=>{observer=new ResizeObserver(resize);if(host.value)observer.observe(host.value);resize();clock=setInterval(()=>now.value=new Date(),1000);document.addEventListener('fullscreenchange',fullChanged);window.addEventListener('resize',resize);window.visualViewport?.addEventListener('resize',resize)})
onBeforeUnmount(()=>{disposed=true;observer?.disconnect();if(clock)clearInterval(clock);if(frame)cancelAnimationFrame(frame);trend?.dispose();typeChart?.dispose();document.removeEventListener('fullscreenchange',fullChanged);window.removeEventListener('resize',resize);window.visualViewport?.removeEventListener('resize',resize)})
</script>

<template>
 <div ref="host" class="panorama" :class="{'motion-paused':!motionEnabled}" data-wall-theme="dark" :aria-busy="loading" :data-fullscreen="fullscreen">
  <div class="panorama-stage" :style="{width:geometry.canvasWidth+'px',height:geometry.canvasHeight+'px',transform:`translate(${geometry.left}px,${geometry.top}px) scale(${geometry.scale})`}">
   <div class="tech-atmosphere" aria-hidden="true"><div class="ambient-halo"/><div class="header-signal"><i/><i/></div></div>
   <header class="command-header">
    <div class="header-start"><RouterLink to="/monitor-wall">‹ 大屏列表</RouterLink><span :class="['sync-state',{bad:!!error||stale}]">● {{error?'同步异常':stale?'快照已过期':loading?'正在同步':'定时同步'}}</span></div>
    <div class="command-title"><span>HELI MONITOR · PANORAMA</span><h1>{{systemSettings.monitor_wall_title}}</h1><div>业务可用性 · 全景运维驾驶舱</div></div>
    <div class="header-end"><button :aria-pressed="motionEnabled" @click="motionEnabled=!motionEnabled">{{motionEnabled?'关闭动效':'开启动效'}}</button><button :aria-pressed="!autoRotate" @click="autoRotate=!autoRotate">{{autoRotate?'暂停轮播':'继续轮播'}}</button><button @click="toggleFull">{{fullscreen?'退出全屏':'⛶ 全屏'}}</button><div class="live-clock"><b>{{now.toLocaleTimeString('zh-CN',{hour12:false})}}</b><small>{{now.toLocaleDateString('zh-CN')}}</small></div></div>
   </header>
   <section class="kpi-strip" aria-label="监控核心指标"><div v-for="item in kpis" :key="item.label"><span>{{item.label}}</span><b :style="{color:item.color}">{{item.value}}<em>{{item.unit}}</em></b></div></section>
   <main class="panorama-grid">
    <WallPanel title="监控状态矩阵" hint="全部任务 · 最近状态" class="status-panel"><div v-for="state in statuses" :key="state[0]" class="state-row"><span><i :style="{background:color(state[0])}"/>{{state[1]}}</span><b>{{snapshot?snapshot.states[state[0]]||0:'—'}}</b><div><i :style="{width:(monitors.length?(snapshot?.states[state[0]]||0)/monitors.length*100:0)+'%',background:color(state[0])}"/></div></div></WallPanel>
    <WallPanel title="实时响应趋势" class="trend-panel"><template #default><div class="trend-controls"><small>{{history?range(history.checked_after)+' — '+range(history.checked_before):'正在读取原始记录'}} · {{history?.series.length||0}} 个原始点</small><select v-model.number="periodHours" aria-label="响应趋势时间周期"><option v-for="period in [1,6,12,24,72,168,720]" :key="period" :value="period">{{period<24?'近 '+period+' 小时':period===720?'近 1 个月':'近 '+period/24+' 天'}}</option></select></div><div ref="trendEl" class="trend-chart"/></template></WallPanel>
    <WallPanel v-model:page="pages.events" title="近期开放事件" :hint="'开放 '+number(snapshot?.open_incidents)+' 条 · 最近 '+incidents.length+' 条'" :total="incidents.length" :page-size="3" :auto-rotate="autoRotate" class="event-panel"><div v-if="!incidents.length" class="empty-state"><strong :class="{attention:!!snapshot?.open_incidents}">{{!snapshot?'正在连接数据':snapshot.open_incidents?'存在待处理事件':'当前无开放事件'}}</strong><small>{{!snapshot?'请稍候':snapshot.open_incidents?'事件详情暂未返回':'以最近一次服务端快照为准'}}</small></div><div v-for="item in pageItems(incidents,pages.events,3)" :key="item.id" class="incident-row"><span>{{item.severity}}</span><b :title="item.title">{{item.title}}</b><small>{{item.business}} · {{time(item.opened_at)}}</small></div></WallPanel>
    <WallPanel title="探测类型分布" :hint="monitors.length+' 项任务'" class="type-panel"><div ref="typeEl" class="type-chart"/></WallPanel>
    <WallPanel v-model:page="pages.nodes" title="业务健康节点" :total="monitors.length" :page-size="6" :auto-rotate="autoRotate" class="node-panel"><div class="health-nodes"><article v-for="item in pageItems(monitors,pages.nodes,6)" :key="item.id" :style="{'--node-color':color(item.status)}"><b :title="item.name">{{item.name}}</b><small :title="item.business">{{item.business}} · {{item.type}}</small><div><span>{{label(item.status)}}</span><strong>{{number(item.latency_ms,2)}} ms</strong></div></article></div><div v-if="!monitors.length" class="empty-state">{{loading?'正在载入任务':'暂无监控任务'}}</div></WallPanel>
    <WallPanel v-model:page="pages.stream" title="实时探测流" hint="最近 10 次原始探测" :total="latest.length" :page-size="5" :auto-rotate="autoRotate" class="stream-panel"><div v-for="point in pageItems(latest,pages.stream,5)" :key="point.id" class="stream-row"><i :style="{background:point.success?'#32d6a4':'#ff7188'}"/><span :title="monitorMap[point.monitor]?.name">{{monitorMap[point.monitor]?.name||point.monitor.slice(0,8)}}</span><b>{{number(point.latency_ms,2)}} ms</b><small>{{time(point.at)}}</small></div><div v-if="!latest.length" class="empty-state">{{loading?'正在读取记录':'周期内暂无探测记录'}}</div></WallPanel>
    <WallPanel v-model:page="pages.sla" title="24H SLA 可用率" :total="sla.length" :page-size="5" :auto-rotate="autoRotate" class="sla-panel"><div v-if="slaUnavailable" class="empty-state">报表不可用或无查看权限</div><div v-else-if="!sla.length" class="empty-state">暂无 SLA 样本</div><div v-for="item in pageItems(sla,pages.sla,5)" :key="item.monitor_id" class="sla-row"><div><b :title="item.monitor_name+' · '+item.business_name">{{item.monitor_name}}</b><span>{{item.availability==null?'—':number(item.availability,3)+'%'}}</span></div><div class="sla-track"><i :style="{width:(item.availability||0)+'%',background:item.availability!=null&&item.availability<99?'#ffbf69':'#32d6a4'}"/></div></div></WallPanel>
    <WallPanel v-model:page="pages.inventory" title="全量监控清单" :total="monitors.length" :page-size="6" :auto-rotate="autoRotate" class="inventory-panel"><div v-for="item in pageItems(monitors,pages.inventory,6)" :key="item.id" class="inventory-row"><i :style="{background:color(item.status)}"/><b :title="item.name+' · '+item.business">{{item.name}}</b><small>{{item.type}}</small><span :style="{color:color(item.status)}">{{label(item.status)}}</span><strong>{{number(item.latency_ms,2)}} ms</strong></div><div v-if="!monitors.length" class="empty-state">暂无监控任务</div></WallPanel>
    <WallPanel title="性能热点 TOP 5" hint="所选周期 · 最慢单次响应" class="performance-panel"><div v-for="(point,index) in slowest" :key="point.id" class="performance-row"><em>{{String(index+1).padStart(2,'0')}}</em><b :title="monitorMap[point.monitor]?.name">{{monitorMap[point.monitor]?.name||point.monitor.slice(0,8)}}</b><span>{{number(point.latency_ms,2)}} ms</span></div><div v-if="!slowest.length" class="empty-state">周期内暂无响应样本</div></WallPanel>
   </main>
   <footer class="cockpit-footer"><span :class="{bad:!!error||stale}">{{error|| (stale?'快照已过期 · ':'服务端快照 ')+time(snapshot?.snapshot_at)}}</span><span>HELI MONITOR · 全域业务可用性监控</span><span>{{Math.round(geometry.width)}} × {{Math.round(geometry.height)}} · {{Math.round(geometry.scale*100)}}% · {{Math.max(5,systemSettings.monitor_wall_refresh_seconds||10)}}s 同步 <button :disabled="loading" @click="load(true)">刷新</button></span></footer>
  </div>
 </div>
</template>

<style scoped>
.panorama{height:var(--wall-available-height,calc(100dvh - 150px));min-height:260px;width:100%;position:relative;overflow:hidden;background:#050f1c;color:#dceeff;color-scheme:dark;border:1px solid #23465f;border-radius:10px;isolation:isolate}.panorama:fullscreen{height:100dvh;width:100vw;min-height:0;border:0;border-radius:0}.panorama-stage{position:absolute;left:0;top:0;width:1920px;height:1080px;transform-origin:0 0;display:grid;grid-template-rows:76px 100px minmax(0,1fr) 24px;gap:14px;padding:22px;box-sizing:border-box;background-image:linear-gradient(#227da80a 1px,transparent 1px),linear-gradient(90deg,#227da80a 1px,transparent 1px),radial-gradient(ellipse at 50% 0,#11547b55,transparent 65%);background-size:36px 36px,36px 36px,100% 100%}.command-header{display:grid;grid-template-columns:1fr 1.8fr 1fr;align-items:center;border-bottom:1px solid #285775;position:relative}.command-header:after{content:'';height:2px;position:absolute;bottom:-1px;left:35%;right:35%;background:#43d1ef;box-shadow:0 0 15px #43d1ef66}.command-title{text-align:center}.command-title>span{font-size:10px;letter-spacing:.22em;color:#78b9d8}.command-title h1{font-size:28px;margin:3px 0;color:#e6f5ff;letter-spacing:.06em;white-space:nowrap}.command-title>div{color:#8db5d3;font-size:11px;letter-spacing:.18em}.header-start{display:flex;align-items:center;gap:16px}.header-start a{color:#a6cfe7;text-decoration:none;font-size:13px}.sync-state{font-size:12px;color:#32d6a4}.bad{color:#ff899a!important}.header-end{display:flex;align-items:center;justify-content:flex-end;gap:12px}.panorama button,.panorama select{background:#112e45;color:#c4e9ff;border:1px solid #2d5a74;border-radius:5px;font-size:12px;padding:5px 10px;cursor:pointer}.panorama button:focus-visible,.panorama select:focus-visible{outline:2px solid #43d1ef}.live-clock{display:grid;text-align:right;gap:3px;min-width:110px}.live-clock b{font-size:24px;font-variant-numeric:tabular-nums}.live-clock small{font-size:11px;color:#88acc7}.kpi-strip{display:grid;grid-template-columns:repeat(8,minmax(0,1fr));border:1px solid #28506a;border-top:2px solid #258fae;border-radius:8px;background:#0b2235}.kpi-strip>div{padding:16px 20px;border-right:1px solid #1a3b52;min-width:0}.kpi-strip>div:last-child{border:0}.kpi-strip span{display:block;color:#8fb4cf;font-size:12px}.kpi-strip b{display:block;font-size:30px;line-height:1.4;margin-top:5px;font-variant-numeric:tabular-nums}.kpi-strip em{font-size:12px;font-style:normal;margin-left:4px}.panorama-grid{min-height:0;display:grid;grid-template-columns:370px minmax(0,1fr) 400px;grid-template-rows:1.12fr 1fr 1fr;gap:14px;grid-template-areas:'status trend events' 'types nodes stream' 'sla inventory performance'}.status-panel{grid-area:status}.trend-panel{grid-area:trend}.event-panel{grid-area:events}.type-panel{grid-area:types}.node-panel{grid-area:nodes}.stream-panel{grid-area:stream}.sla-panel{grid-area:sla}.inventory-panel{grid-area:inventory}.performance-panel{grid-area:performance}.state-row{height:25px;display:grid;grid-template-columns:88px 32px 1fr;align-items:center;gap:8px;font-size:13px}.state-row>span{display:flex;align-items:center;gap:8px}.state-row>span>i,.stream-row>i,.inventory-row>i{display:block;width:6px;height:6px;border-radius:50%}.state-row>b{text-align:right}.state-row>div{height:5px;background:#16364e;border-radius:3px}.state-row>div>i{display:block;height:100%;border-radius:3px}.trend-controls{height:28px;display:flex;align-items:center;justify-content:space-between;gap:8px}.trend-controls small{font-size:11px;color:#79a4c1}.trend-controls select{padding:2px 8px}.trend-chart{height:calc(100% - 28px);width:100%}.type-chart{height:100%;width:100%}.empty-state{height:100%;display:flex;align-items:center;justify-content:center;flex-direction:column;gap:10px;color:#7eabc7;font-size:13px;text-align:center}.empty-state strong{color:#32d6a4;font-size:18px}.empty-state strong.attention{color:#ffbf69}.empty-state small{font-size:11px}.incident-row{height:53px;box-sizing:border-box;margin-bottom:7px;padding-left:10px;border-left:2px solid #ff7188;display:grid;grid-template-columns:70px 1fr;gap:4px 8px;align-content:center}.incident-row>span{font-size:10px;color:#ff8d9d}.incident-row>b{font-size:13px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.incident-row>small{grid-column:1/-1;font-size:11px;color:#8cafc9}.health-nodes{height:100%;display:grid;grid-template-columns:repeat(3,minmax(0,1fr));grid-template-rows:repeat(2,minmax(0,1fr));gap:8px}.health-nodes article{min-height:0;min-width:0;border:1px solid #24475f;border-left:2px solid var(--node-color);border-radius:5px;background:#102a40;padding:9px 11px;display:flex;flex-direction:column;justify-content:center;gap:5px}.health-nodes article>b{font-size:14px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.health-nodes article>small{font-size:10px;color:#81a7c1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.health-nodes article>div{display:flex;align-items:center;justify-content:space-between;font-size:11px}.health-nodes article span{color:var(--node-color)}.health-nodes article strong{font-weight:500;color:#b8d7ee}.stream-row{height:29px;display:grid;grid-template-columns:6px minmax(0,1fr) 80px 60px;align-items:center;gap:8px;border-bottom:1px solid #1b3b52;font-size:12px}.stream-row>span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.stream-row>b{font-size:11px;color:#60c9ee;font-weight:500;text-align:right}.stream-row>small{font-size:10px;color:#7d9eb8;text-align:right}.sla-row{height:29px}.sla-row>div:first-child{display:flex;justify-content:space-between;gap:10px;align-items:center}.sla-row b{font-size:12px;font-weight:500;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.sla-row span{font-size:12px;color:#37d6ad;flex:none}.sla-track{height:3px;background:#183b51;margin-top:5px;border-radius:2px}.sla-track i{display:block;height:100%;border-radius:2px}.inventory-row{height:25px;display:grid;grid-template-columns:6px minmax(0,1fr) 80px 46px 92px;align-items:center;gap:9px;border-bottom:1px solid #1b3b52;font-size:12px}.inventory-row>b{font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.inventory-row>small{font-size:10px;color:#83a9c3}.inventory-row>span{font-size:11px}.inventory-row>strong{font-weight:500;font-size:11px;color:#b3d3e7;text-align:right}.performance-row{height:29px;display:grid;grid-template-columns:26px minmax(0,1fr) 85px;gap:8px;align-items:center;border-bottom:1px solid #1b3b52}.performance-row em{color:#42c9ec;font-style:normal;font-size:12px}.performance-row b{font-size:12px;font-weight:500;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.performance-row span{font-size:11px;color:#ffbf69;text-align:right}.cockpit-footer{display:flex;align-items:center;justify-content:space-between;gap:12px;color:#6e99b8;font-size:11px;border-top:1px solid #24465e;padding-top:4px}.cockpit-footer button{padding:1px 7px;margin-left:6px;font-size:10px}.panorama button:disabled{opacity:.4;cursor:default}

/* Calm motion frames the information without sweeping over charts or text. */
.tech-atmosphere{position:absolute;inset:0;overflow:hidden;pointer-events:none;z-index:0}
.panorama-stage>header,.panorama-stage>section,.panorama-stage>main,.panorama-stage>footer{position:relative;z-index:1}
.panorama-stage{background-image:radial-gradient(ellipse at 50% 0,#103e5955,transparent 60%),linear-gradient(#1e698205 1px,transparent 1px),linear-gradient(90deg,#1e698205 1px,transparent 1px);background-size:100% 100%,48px 48px,48px 48px}
.ambient-halo{position:absolute;top:-170px;left:calc(50% - 510px);width:1020px;height:300px;border-radius:50%;background:radial-gradient(ellipse,#208cba16,transparent 68%);animation:ambient-breathe 12s ease-in-out infinite}
.header-signal{position:absolute;top:97px;left:calc(50% - 340px);width:680px;height:1px;overflow:hidden;background:linear-gradient(90deg,transparent,#4cb5d536,transparent)}
.header-signal i{position:absolute;left:0;top:0;width:110px;height:1px;background:linear-gradient(90deg,transparent,#9ae8f0aa,transparent);animation:signal-pass 10s cubic-bezier(.4,0,.6,1) infinite}
.header-signal i+i{animation-delay:-5s;opacity:.35}
.command-header:after{height:1px;left:40%;right:40%;background:linear-gradient(90deg,transparent,#70c9dd,transparent);box-shadow:none}
.command-title h1{text-shadow:0 0 18px #49b7ce18}
.command-title>span{color:#81b8ce;letter-spacing:3px}
.kpi-strip{border-top:1px solid #34657b;background:linear-gradient(180deg,#102a3c,#0c2133);box-shadow:inset 0 1px #9edff208}
.kpi-strip>div{position:relative}
.kpi-strip>div:after{content:'';position:absolute;left:20px;bottom:9px;width:22px;height:2px;border-radius:2px;background:#69bed54d}
.panorama-grid :deep(.wall-panel){background:linear-gradient(155deg,#0d2235,#0a1b2b);box-shadow:inset 0 1px #a8e8ff06;animation:panel-reveal .6s ease-out both}
.panorama-grid :deep(.wall-panel:nth-child(3n+2)){animation-delay:.06s}
.panorama-grid :deep(.wall-panel:nth-child(3n)){animation-delay:.12s}
.panorama-grid :deep(.wall-panel:before){width:2px;height:12px;top:16px;background:#6fc6dc;opacity:.8}
.panorama-grid :deep(.wall-panel:after){content:'';position:absolute;left:16px;right:16px;top:0;height:1px;background:linear-gradient(90deg,transparent,#6bc5dd38,transparent);pointer-events:none;animation:edge-breathe 10s ease-in-out infinite}
.panorama-grid :deep(.wall-panel:nth-child(2n):after){animation-delay:-5s}
.health-nodes article{position:relative;border-left-width:1px;background:#10283a;transition:border-color .4s}
.health-nodes article>b{padding-left:10px}
.health-nodes article:before{content:'';position:absolute;left:10px;top:50%;margin-top:-21px;width:4px;height:4px;border-radius:50%;background:var(--node-color);box-shadow:0 0 0 3px color-mix(in srgb,var(--node-color) 9%,transparent);animation:node-breathe 6s ease-in-out infinite}
.health-nodes article:nth-child(2n):before{animation-delay:-3s}
.state-row>div>i,.sla-track i{transition:width .6s ease}
.header-end{gap:7px}.header-end button{padding:5px 7px;font-size:11px;border-color:#2a4a60;background:#102638}
@keyframes ambient-breathe{0%,100%{opacity:.45}50%{opacity:.9}}
@keyframes signal-pass{0%{transform:translateX(-110px);opacity:0}15%,70%{opacity:.8}100%{transform:translateX(790px);opacity:0}}
@keyframes edge-breathe{0%,100%{opacity:.35}50%{opacity:.9}}
@keyframes node-breathe{0%,100%{opacity:.65}50%{opacity:1}}
@keyframes panel-reveal{from{opacity:0}to{opacity:1}}
.motion-paused *,.motion-paused :deep(*),.motion-paused :deep(*:before),.motion-paused :deep(*:after){animation:none!important;transition:none!important}
.motion-paused .header-signal i{display:none}
@media(prefers-reduced-motion:reduce){.panorama *,.panorama :deep(*),.panorama :deep(*:before),.panorama :deep(*:after){animation:none!important;transition:none!important}.header-signal i{display:none}}
</style>
