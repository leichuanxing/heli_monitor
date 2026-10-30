<script setup lang="ts">
import { defineAsyncComponent, computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import client from '../api/client'
import type { AssetOptions } from '../api/assetTypes'
import type { BatchStart, BatchStatus } from '../api/monitorTypes'
import type { FieldConfig, ResourceConfig } from '../config/resources'
import MonitorTaskForm from '../components/MonitorTaskForm.vue'
import TableActionButton from '../components/TableActionButton.vue'
const MonitorHistory=defineAsyncComponent(()=>import('./MonitorHistoryView.vue'))
const historyVisible=ref(false),historyMonitorId=ref('')
const props=defineProps<{config:ResourceConfig}>(),rows=ref<any[]>([]),loading=ref(false),saving=ref(false),search=ref(''),dialog=ref(false),form=ref<any>({}),batchTesting=ref(false),testDialog=ref(false),testReport=ref<any>({results:[]}),relationOptions=ref<Record<string,any[]>>({})
const page=ref(1),pageSize=ref(20),total=ref(0)
const router=useRouter(),selectedRows=ref<any[]>([]),typeFilter=ref(''),enabledFilter=ref(''),businessFilter=ref(''),canManage=ref(false),running=ref<string[]>([])
const canManageAssets=ref(false),assetGroup=ref(''),assetEnabled=ref(''),assetArchived=ref('')
const isAsset=computed(()=>['business-systems','business-groups','tags'].includes(props.config.endpoint))
const isBusiness=computed(()=>props.config.endpoint==='business-systems')
const isMonitor=computed(()=>props.config.endpoint==='monitors'),editable=computed(()=>isAsset.value?canManageAssets.value:!isMonitor.value||canManage.value)
const batchToken=ref(''),batchDone=ref(true),batchConnectionLost=ref(false)
let pollTimer:ReturnType<typeof setTimeout>|undefined,disposed=false,batchGeneration=0
const types=['HTTP','API','TCP','PING','DNS','SSL','MSSQL','POSTGRESQL','MYSQL','MONGODB']
function assetFilters(){return {search:search.value,group:assetGroup.value||undefined,is_enabled:assetEnabled.value||undefined,is_archived:assetArchived.value||undefined}}
function filters(){return {search:search.value,monitor_type:typeFilter.value||undefined,is_enabled:enabledFilter.value||undefined,business:businessFilter.value||undefined}}
let loadVersion=0
function searchRows(){page.value=1;load()}
const monitorConfigRef=ref<InstanceType<typeof MonitorTaskForm>>()
const deepCopy=<T>(value:T):T=>value==null?value:JSON.parse(JSON.stringify(value))
const display=(row:any,field:FieldConfig)=>field.key==='current_status'?({UP:'正常',DOWN:'故障',DEGRADED:'降级',PAUSED:'已暂停',MAINTENANCE:'维护中',PENDING:'待探测',UNKNOWN:'未知'} as any)[row[field.key]]||row[field.key]:field.type==='boolean'?(row[field.key]==null?(field.key==='service_available'&&row.last_checked_at?'待确认':'未探测'):row[field.key]?'是':'否'):field.type==='datetime'&&row[field.key]?new Date(row[field.key]).toLocaleString():row[field.key]
async function load(){const version=++loadVersion;loading.value=true;try{const{data}=await client.get(`/${props.config.endpoint}/`,{params:{...(isMonitor.value?filters():isBusiness.value?assetFilters():{search:search.value}),page:page.value,page_size:pageSize.value}});if(version!==loadVersion)return;rows.value=data.results||data;total.value=data.count??rows.value.length}catch(e:any){if(version===loadVersion)ElMessage.error(e.response?.data?.message||'加载失败')}finally{if(version===loadVersion)loading.value=false}}
async function loadRelations(){relationOptions.value={};if(isAsset.value){const{data}=await client.get<AssetOptions>('/business-systems/options/');relationOptions.value=data;if(props.config.endpoint==='business-groups')relationOptions.value['business-groups']=data['business-groups'].filter((item:any)=>item.id!==form.value.id);return;}if(isMonitor.value){const{data}=await client.get('/monitors/options/');relationOptions.value={'business-systems':data.businesses,tags:data.tags};return;}for(const field of props.config.fields||[])if(field.type==='relation'&&field.endpoint&&!relationOptions.value[field.endpoint]){const{data}=await client.get(`/${field.endpoint}/`,{params:{page_size:200}});relationOptions.value[field.endpoint]=data.results||data}}
function fresh(){const value:any={};for(const field of props.config.fields||[]){const initial=field.default!==undefined?deepCopy(field.default):(field.multiple?[]:null);value[field.key]=field.type==='json'&&!(props.config.endpoint==='monitors'&&field.key==='config')?JSON.stringify(initial??{},null,2):initial}return value}
function openCreate(){form.value=fresh();dialog.value=true;loadRelations().catch(()=>ElMessage.error('关联选项加载失败'))}
function openEdit(row:any){form.value={...row,config:deepCopy(row.config||{})};for(const field of props.config.fields||[])if(field.type==='json'&&!(props.config.endpoint==='monitors'&&field.key==='config'))form.value[field.key]=JSON.stringify(row[field.key]??field.default??{},null,2);dialog.value=true;loadRelations().catch(()=>ElMessage.error('关联选项加载失败'))}
const labelOf=(item:any)=>item.name||item.username||item.code||item.number||item.id
const targetHints:Record<string,string>={HTTP:'完整 URL，例如：https://www.example.com/health',API:'完整接口 URL，例如：https://api.example.com/v1/health',TCP:'主机:端口，例如：10.0.0.8:8080',PING:'主机名或 IP，例如：192.168.1.10',DNS:'待解析域名，例如：www.example.com',SSL:'域名:端口，例如：www.example.com:443',MSSQL:'SQL Server 主机:端口，例如：10.0.0.10:1433',POSTGRESQL:'PostgreSQL 主机:端口，例如：10.0.0.11:5432',MYSQL:'MySQL/MariaDB 主机:端口，例如：10.0.0.12:3306',MONGODB:'MongoDB 主机:端口，例如：10.0.0.13:27017'}
const configHints:Record<string,string>={HTTP:'可配置 method、headers、params、expected_status、keywords、regex、follow_redirects',API:'支持请求头、查询参数、JSON/表单/文本请求体、响应断言，以及 bearer、basic、api_key、oauth2_client_credentials 认证',TCP:'可配置 send（发送内容）、expect（期望返回内容）',PING:'可配置 count（1-10）和 timeout',DNS:'可配置 record_type（A/AAAA/CNAME/MX/TXT）、server、expected',SSL:'可配置 warn_days（证书到期预警天数）',MSSQL:'必填 database、username、password；可选 query、expected_value、tds_version',POSTGRESQL:'必填 database、username、password；可选 query、expected_value、sslmode',MYSQL:'适用于 MySQL/MariaDB；必填 database、username、password；可选 query、expected_value、use_tls',MONGODB:'必填 database、username、password；可选 auth_source、use_tls'}
const configExamples:Record<string,string>={HTTP:'{\n  "method": "GET",\n  "expected_status": [200, 204],\n  "headers": {"Accept": "application/json"}\n}',API:'{\n  "method": "POST",\n  "auth": {"type": "bearer", "token": "请输入令牌"},\n  "json": {"ping": true},\n  "expected_status": [200, 201]\n}',TCP:'{\n  "send": "PING\\r\\n",\n  "expect": "PONG"\n}',PING:'{\n  "count": 3,\n  "timeout": 5\n}',DNS:'{\n  "record_type": "A",\n  "expected": ["1.2.3.4"]\n}',SSL:'{\n  "warn_days": 30\n}',MSSQL:'{\n  "database": "master",\n  "username": "monitor",\n  "password": "请输入密码",\n  "query": "SELECT 1",\n  "expected_value": 1\n}',POSTGRESQL:'{\n  "database": "postgres",\n  "username": "monitor",\n  "password": "请输入密码",\n  "sslmode": "prefer",\n  "query": "SELECT 1"\n}',MYSQL:'{\n  "database": "mysql",\n  "username": "monitor",\n  "password": "请输入密码",\n  "use_tls": false,\n  "query": "SELECT 1"\n}',MONGODB:'{\n  "database": "admin",\n  "username": "monitor",\n  "password": "请输入密码",\n  "auth_source": "admin",\n  "use_tls": false\n}'}
function fieldPlaceholder(field:FieldConfig){if(props.config.endpoint==='monitors'&&field.key==='target')return targetHints[form.value.monitor_type]||'';if(props.config.endpoint==='monitors'&&field.key==='config')return configExamples[form.value.monitor_type]||'{}';return field.placeholder||''}
function fieldHelp(field:FieldConfig){if(props.config.endpoint==='monitors'&&field.key==='config')return configHints[form.value.monitor_type]||'';return field.help||''}
async function save(){saving.value=true;try{if(props.config.endpoint==='monitors')form.value.config=monitorConfigRef.value?.normalize()||form.value.config;const payload={...form.value};for(const field of props.config.fields||[])if(field.type==='json'&&typeof payload[field.key]==='string')payload[field.key]=JSON.parse(payload[field.key]||'{}');payload.id?await client.patch(`/${props.config.endpoint}/${payload.id}/`,payload):await client.post(`/${props.config.endpoint}/`,payload);dialog.value=false;ElMessage.success('保存成功');await load()}catch(e:any){ElMessage.error(JSON.stringify(e.response?.data?.details||e.response?.data||e.message||'保存失败'))}finally{saving.value=false}}
async function remove(row:any){try{await ElMessageBox.confirm(props.config.endpoint==='monitors'?'确认永久删除该探测任务？历史探测结果、故障事件及关联通知也将删除，无法恢复。':'确认删除该记录？此操作不可撤销。','删除确认',{type:'warning'});await client.delete(`/${props.config.endpoint}/${row.id}/`);if(rows.value.length===1&&page.value>1)page.value--;ElMessage.success(props.config.endpoint==='monitors'?'探测任务及相关数据已永久删除':'删除成功');await load()}catch(e:any){if(e==='cancel'||e==='close')return;ElMessage.error(e.response?.data?.details?.detail||e.response?.data?.detail||'删除失败，请检查关联数据或权限')}}
function formatError(e:any){return JSON.stringify(e.response?.data?.details||e.response?.data||e.message||'操作失败')}
async function action(row:any,name:string){
 if(running.value.includes(row.id))return
 running.value.push(row.id)
 try{const path=name==='test-channel'?'test':name,{data}=await client.post(`/${props.config.endpoint}/${row.id}/${path}/`,{},{timeout:70000})
  if(isMonitor.value&&name==='test'){
   testReport.value={success:data.success,total:1,passed:Number(data.success),failed:Number(!data.success),completed:1,results:[{...data,name:row.name,type:row.monitor_type,state:'SUCCESS'}]};batchDone.value=true;testDialog.value=true
  }else ElMessage.success(name==='rotate-token'?`新令牌：${data.token}`:'操作成功')
  await load()
 }catch(e:any){ElMessage.error(formatError(e))}finally{running.value=running.value.filter(id=>id!==row.id)}
}
async function pollBatch(){
 const generation=batchGeneration
 if(!batchToken.value||disposed||!isMonitor.value)return
 try{const{data}=await client.get<BatchStatus>('/monitors/batch-status/',{params:{token:batchToken.value}})
  if(disposed||!isMonitor.value||generation!==batchGeneration)return
  batchConnectionLost.value=false
  testReport.value={...data,success:data.done&&data.failed===0&&data.skipped===0};batchDone.value=data.done
  if(data.done){batchTesting.value=false;sessionStorage.removeItem('monitor_batch_token');await load();return}
  pollTimer=setTimeout(pollBatch,2000)
 }catch(e:any){
  if(disposed||!isMonitor.value||generation!==batchGeneration)return
  if([400,401,403,404].includes(e?.response?.status)){batchTesting.value=false;batchDone.value=true;sessionStorage.removeItem('monitor_batch_token');ElMessage.error(formatError(e));return}
  batchConnectionLost.value=true
  // Keep the signed token across temporary network/server failures.
  pollTimer=setTimeout(pollBatch,5000)
 }

}
async function testAll(){
 if(isMonitor.value){
  if(batchTesting.value){testDialog.value=true;return}
  batchTesting.value=true
  try{
   let ids=selectedRows.value.map(r=>r.id)
   if(!ids.length){const{data}=await client.get('/monitors/',{params:{...filters(),is_enabled:true,page_size:100}});if(data.count>100)throw new Error('当前范围超过 100 项，请筛选或勾选需要探测的任务');ids=(data.results||data).map((r:any)=>r.id)}
   if(!ids.length)throw new Error('当前范围内没有已启用的探测任务')
   const{data}=await client.post<BatchStart>('/monitors/run-batch/',{ids})
   batchToken.value=data.token;sessionStorage.setItem('monitor_batch_token',data.token);batchDone.value=false
   testReport.value={total:data.total,completed:0,passed:0,failed:0,skipped:0,results:[]};testDialog.value=true;pollBatch()
  }catch(e:any){batchTesting.value=false;ElMessage.error(formatError(e))}
  return
 }
 batchTesting.value=true;try{const{data}=await client.post(`/${props.config.endpoint}/test-all/`);testReport.value=data;testDialog.value=true} catch(e:any){ElMessage.error(formatError(e))}finally{batchTesting.value=false}
}
async function toggleMonitors(enabled:boolean,row?:any){
 const ids=row?[row.id]:selectedRows.value.map(r=>r.id)
 if(!ids.length){ElMessage.warning('请先勾选任务');return}
 try{await client.post('/monitors/bulk-enable/',{ids,enabled});ElMessage.success(enabled?'任务已启用':'任务已暂停');await load()}catch(e:any){ElMessage.error(formatError(e))}
}
async function copyMonitor(row:any){try{const{data}=await client.post(`/monitors/${row.id}/copy/`);ElMessage.success('副本已创建并保持暂停，可修改后启用');await load();openEdit(data)}catch(e:any){ElMessage.error(formatError(e))}}
function history(row:any){historyMonitorId.value=row.id;historyVisible.value=true}
function fieldMin(field:FieldConfig){return isMonitor.value&&['interval_seconds','timeout_seconds','failure_threshold','recovery_threshold'].includes(field.key)?field.key==='interval_seconds'?5:1:0}
function fieldMax(field:FieldConfig){return field.key==='sla_target'?100:!isMonitor.value?undefined:field.key==='timeout_seconds'?30:field.key==='interval_seconds'?86400:['failure_threshold','recovery_threshold'].includes(field.key)?100:undefined}

function reportMessage(row:any){
 if(row.error_summary||row.message)return row.error_summary||row.message
 if(row.state&&!['SUCCESS','FAILURE','REVOKED','SKIPPED'].includes(row.state))return '正在排队或执行'
 if(row.metrics?.warning)return '证书已进入预警期，任务状态会相应降级'
 return row.status_code?'HTTP '+row.status_code:row.success===false?'探测未通过':'测试成功'
}
const actionLabel=(name:string)=>({test:'立即探测',acknowledge:'确认',close:'关闭','test-channel':'测试渠道','rotate-token':'轮换令牌'}[name]||name)
const actionIcon=(name:string):'run'|'check'|'close'|'refresh'=>name==='test'||name==='test-channel'?'run':name==='acknowledge'?'check':name==='close'?'close':'refresh'
function restoreBatch(){
 batchGeneration++
 if(pollTimer)clearTimeout(pollTimer)
 batchTesting.value=false;batchDone.value=true;batchConnectionLost.value=false
 const token=isMonitor.value?sessionStorage.getItem('monitor_batch_token'):null
 if(token){batchToken.value=token;batchTesting.value=true;batchDone.value=false;pollBatch()}
}
watch(()=>props.config.endpoint,()=>{restoreBatch();testDialog.value=false;selectedRows.value=[];assetGroup.value='';assetEnabled.value='';assetArchived.value='';typeFilter.value='';enabledFilter.value='';businessFilter.value='';if(isMonitor.value||isAsset.value)loadRelations().catch(()=>undefined);search.value='';page.value=1;rows.value=[];total.value=0;dialog.value=false;load()});onMounted(async()=>{load();{try{const{data}=await client.get('/auth/me/');canManage.value=data.is_superuser||data.permissions.includes('monitor.manage');canManageAssets.value=data.is_superuser||data.permissions.includes('asset.manage');if(isAsset.value)await loadRelations();if(isMonitor.value)await loadRelations();restoreBatch()}catch{ElMessage.error('权限或表单选项加载失败')}}});onBeforeUnmount(()=>{loadVersion++;disposed=true;if(pollTimer)clearTimeout(pollTimer)})
</script>
<template>
<div class="heading"><div><h2>{{config.title}}</h2><small>共 {{total}} 条记录</small></div><div class="toolbar"><el-input v-model="search" placeholder="搜索" clearable @clear="searchRows" @keyup.enter="searchRows"/><el-button @click="searchRows">查询</el-button><el-button v-if="editable&&(isMonitor||config.endpoint==='notification-channels')" @click="testAll">{{isMonitor?(batchTesting?'查看探测进度':selectedRows.length?'探测所选任务':'探测当前范围'):'测试全部渠道'}}</el-button><el-button v-if="!config.readonly&&editable" type="primary" @click="openCreate">新增</el-button></div></div>
<div v-if="isMonitor" class="monitor-filters"><el-select v-model="typeFilter" clearable placeholder="全部探测类型" @change="searchRows"><el-option v-for="t in types" :key="t" :value="t"/></el-select><el-select v-model="enabledFilter" clearable placeholder="全部启停状态" @change="searchRows"><el-option label="已启用" value="true"/><el-option label="已暂停" value="false"/></el-select><el-select v-model="businessFilter" clearable filterable placeholder="全部业务系统" @change="searchRows"><el-option v-for="b in relationOptions['business-systems']||[]" :key="b.id" :label="b.name" :value="b.id"/></el-select><template v-if="editable"><el-button :disabled="!selectedRows.length" @click="toggleMonitors(true)">启用所选</el-button><el-button :disabled="!selectedRows.length" @click="toggleMonitors(false)">暂停所选</el-button></template><small>勾选 {{selectedRows.length}} 项 · 批量操作最多 100 项</small></div>
<div v-if="isBusiness" class="monitor-filters" style="display:flex;gap:10px;margin-bottom:14px">
<el-select v-model="assetGroup" clearable placeholder="全部业务分组" @change="searchRows"><el-option v-for="item in relationOptions['business-groups']||[]" :key="item.id" :label="item.name" :value="item.id"/></el-select>
<el-select v-model="assetEnabled" clearable placeholder="全部启停状态" @change="searchRows"><el-option label="已启用" value="true"/><el-option label="已停用" value="false"/></el-select>
<el-select v-model="assetArchived" clearable placeholder="全部归档状态" @change="searchRows"><el-option label="未归档" value="false"/><el-option label="已归档" value="true"/></el-select>
</div>
<p class="table-scroll-hint">可左右滑动表格查看完整信息与操作</p><el-card><el-table v-loading="loading" :data="rows" empty-text="暂无数据" stripe class="resource-table" row-key="id" @selection-change="selectedRows=$event"><el-table-column v-if="isMonitor&&editable" type="selection" width="46"/><el-table-column v-if="isMonitor" prop="business_name" label="业务系统" min-width="150" show-overflow-tooltip/><el-table-column v-for="column in config.columns" :key="column.key" :prop="column.key" :label="column.label" min-width="130" show-overflow-tooltip><template #default="scope"><el-tag v-if="column.type==='boolean'" :type="scope.row[column.key]?'success':'info'">{{display(scope.row,column)}}</el-tag><span v-else>{{display(scope.row,column)}}</span></template></el-table-column><el-table-column v-if="isMonitor||editable&&(!config.readonly||config.actions?.length)" label="操作" :width="isMonitor?380:config.readonly?Math.max(150,(config.actions?.length||0)*82+28):Math.max(150,(config.actions?.length||0)*88+132)" fixed="right" align="center"><template #default="scope"><div class="row-actions"><template v-if="isMonitor"><TableActionButton icon="refresh" label="历史数据" @click="history(scope.row)"/><template v-if="editable"><TableActionButton icon="toggle" :label="scope.row.is_enabled?'暂停':'启用'" icon-only @click="toggleMonitors(!scope.row.is_enabled,scope.row)"/><TableActionButton icon="refresh" label="复制" icon-only @click="copyMonitor(scope.row)"/></template></template><TableActionButton v-for="name in editable?config.actions:[]" :key="name" :icon="actionIcon(name)" :label="actionLabel(name)" :disabled="running.includes(scope.row.id)||(isMonitor&&batchTesting)" tone="primary" @click="action(scope.row,name)"/><template v-if="!config.readonly&&editable"><TableActionButton icon="edit" label="编辑" tone="primary" @click="openEdit(scope.row)"/><TableActionButton icon="delete" label="删除" tone="danger" icon-only @click="remove(scope.row)"/></template></div></template></el-table-column></el-table><el-pagination v-model:current-page="page" v-model:page-size="pageSize" :total="total" :page-sizes="[20,50,100]" layout="total, sizes, prev, pager, next" background @current-change="load" @size-change="searchRows"/></el-card>
<el-dialog v-model="dialog" :title="form.id?'编辑'+config.title:'新增'+config.title" :width="isMonitor?'min(960px, calc(100vw - 24px))':'680px'" :class="{'monitor-edit-dialog':isMonitor}" :top="isMonitor?'4vh':'15vh'" :destroy-on-close="isMonitor" :close-on-click-modal="!saving" :close-on-press-escape="!saving" :show-close="!saving"><MonitorTaskForm v-if="isMonitor" ref="monitorConfigRef" v-model="form" :businesses="relationOptions['business-systems']||[]" :tags="relationOptions.tags||[]"/><el-form v-else label-width="140px"><el-form-item v-for="field in config.fields" :key="field.key" :label="field.label" :required="field.required"><el-switch v-if="field.type==='boolean'" v-model="form[field.key]"/><el-input-number v-else-if="field.type==='number'" v-model="form[field.key]" :min="fieldMin(field)" :max="fieldMax(field)" :precision="field.key==='sla_target'?3:0" :step="field.key==='sla_target'?0.001:1" :placeholder="fieldPlaceholder(field)" style="width:100%"/><el-select v-else-if="field.type==='select'" v-model="form[field.key]" style="width:100%"><el-option v-for="option in field.options" :key="option" :label="option" :value="option"/></el-select><el-select v-else-if="field.type==='relation'" v-model="form[field.key]" :multiple="field.multiple" clearable filterable style="width:100%"><el-option v-for="item in relationOptions[field.endpoint||'']||[]" :key="item.id" :label="labelOf(item)" :value="item.id"/></el-select><el-date-picker v-else-if="field.type==='datetime'" v-model="form[field.key]" type="datetime" value-format="YYYY-MM-DDTHH:mm:ssZ" style="width:100%"/><el-input v-else-if="field.type==='textarea'||field.type==='json'" v-model="form[field.key]" type="textarea" :rows="field.type==='json'?9:3" :placeholder="fieldPlaceholder(field)"/><el-input v-else v-model="form[field.key]" :placeholder="fieldPlaceholder(field)"/><small v-if="fieldHelp(field)" class="field-help">{{fieldHelp(field)}}</small></el-form-item></el-form><template #footer><el-button :disabled="saving" @click="dialog=false">取消</el-button><el-button type="primary" :loading="saving" @click="save">保存</el-button></template></el-dialog>
<el-dialog v-model="testDialog" :title="isMonitor?'探测执行结果':'全部通知渠道测试结果'" width="860px"><el-progress v-if="isMonitor" :percentage="Math.round((testReport.completed||0)/Math.max(testReport.total||1,1)*100)"/><el-alert v-if="isMonitor&&batchConnectionLost" title="连接暂时中断，正在自动重试；后台任务继续执行。" type="warning" :closable="false"/><el-alert v-if="isMonitor&&!batchDone" title="探测在后台执行，关闭窗口不影响任务；返回页面可继续查看进度。" type="info" :closable="false"/><div class="test-summary" :class="testReport.success?'passed':'failed'"><b>{{isMonitor&&!batchDone?'正在执行':testReport.success?'全部通过':'执行完成'}}</b><span>共 {{testReport.total}} 项，通过 {{testReport.passed}} 项，失败 {{testReport.failed}} 项<span v-if="isMonitor">，跳过 {{testReport.skipped||0}} 项</span></span></div><el-table :data="testReport.results" max-height="480"><el-table-column :label="config.endpoint==='monitors'?'业务 / 探测':'渠道'" min-width="190"><template #default="s"><b>{{s.row.business||s.row.business_name||s.row.name||s.row.monitor_name}}</b><small>{{s.row.monitor_name||s.row.type||s.row.monitor_type}}</small></template></el-table-column><el-table-column label="类型" width="120"><template #default="s">{{s.row.monitor_type||s.row.type}}</template></el-table-column><el-table-column label="结果" width="90"><template #default="s"><el-tag :type="s.row.success===true?(s.row.metrics?.warning?'warning':'success'):s.row.success===false||s.row.state==='FAILURE'?'danger':'info'">{{s.row.success===true?(s.row.metrics?.warning?'预警':'通过'):s.row.success===false||s.row.state==='FAILURE'?'失败':s.row.state==='SKIPPED'?'跳过':'执行中'}}</el-tag></template></el-table-column><el-table-column label="耗时" width="110"><template #default="s">{{s.row.latency_ms??'—'}} ms</template></el-table-column><el-table-column label="说明" min-width="240"><template #default="s">{{reportMessage(s.row)}}</template></el-table-column></el-table><template #footer><el-button type="primary" @click="testDialog=false">完成</el-button></template></el-dialog>
<el-dialog v-model="historyVisible" title="任务历史数据" width="94%" top="3vh" destroy-on-close append-to-body>
 <div class="history-dialog-content"><MonitorHistory v-if="historyVisible" :monitor-id="historyMonitorId"/></div>
 <template #footer><el-button @click="historyVisible=false">关闭</el-button></template>
</el-dialog>
</template>
<style scoped>.heading{display:flex;align-items:center;justify-content:space-between;margin-bottom:18px}.heading h2{margin:0}.heading small{color:var(--muted)}.toolbar{display:flex;gap:8px;flex-wrap:wrap}.monitor-filters{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:15px}.monitor-filters .el-select{width:170px}.monitor-filters small{color:var(--muted)}.toolbar .el-input{width:230px}.resource-table :deep(.el-table__cell){padding:11px 0}.resource-table :deep(.el-table-fixed-column--right){background:var(--surface)}.resource-table :deep(.el-table__row--striped .el-table-fixed-column--right){background:var(--surface-subtle)}.row-actions{display:flex;align-items:center;justify-content:center;gap:6px;flex-wrap:nowrap;white-space:nowrap;padding:2px 4px;min-width:max-content}.row-actions :deep(.table-action){flex:0 0 auto}.test-summary{display:flex;align-items:center;justify-content:space-between;padding:14px 16px;margin-bottom:14px;border-radius:6px}.test-summary.passed{color:var(--success);background:var(--surface-subtle);border:1px solid #c7e7d5}.test-summary.failed{color:var(--danger);background:var(--surface-subtle);border:1px solid #efd0d0}.test-summary span{font-size:12px}.el-table small{display:block;color:var(--muted);margin-top:4px}.monitor-hint{margin-bottom:18px}.field-help{display:block;width:100%;color:var(--muted);line-height:1.5;margin-top:5px}
:global(.monitor-edit-dialog .el-dialog__body){padding:14px 24px;max-height:calc(92dvh - 140px);overflow-y:auto;overscroll-behavior:contain}:global(.monitor-edit-dialog .el-dialog__header){padding-bottom:12px}:global(.monitor-edit-dialog .el-dialog__footer){padding-top:12px}@media(max-width:640px){:global(.monitor-edit-dialog .el-dialog__body){padding:12px 16px}}
</style>
