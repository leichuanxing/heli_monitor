<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import MonitorConfigFields from './MonitorConfigFields.vue'

const props = defineProps<{ businesses: Array<{id:string;name:string}>; tags: Array<{id:string;name:string}> }>()
const task = defineModel<Record<string, any>>({ required: true })
const protocol = ref<InstanceType<typeof MonitorConfigFields>>()
const advanced = ref<string[]>([])
const types = ['HTTP','API','TCP','PING','DNS','SSL','MSSQL','POSTGRESQL','MYSQL','MONGODB']
const recommendations: Record<string, [number, number]> = { HTTP:[60,10],API:[60,10],TCP:[60,5],PING:[30,5],DNS:[300,5],SSL:[3600,10],MSSQL:[60,10],POSTGRESQL:[60,10],MYSQL:[60,10],MONGODB:[60,10] }
const suggested = computed(() => recommendations[task.value.monitor_type] || recommendations.HTTP)
const hints: Record<string,string> = { HTTP:'https://example.com/health',API:'https://api.example.com/v1/health',TCP:'10.0.0.8:8080',PING:'192.168.1.10 或主机名',DNS:'www.example.com',SSL:'example.com:443',MSSQL:'10.0.0.10:1433',POSTGRESQL:'10.0.0.11:5432',MYSQL:'10.0.0.12:3306',MONGODB:'10.0.0.13:27017' }
const businessOptions = computed(() => task.value.business && !props.businesses.some(item=>item.id===task.value.business) ? [{id:task.value.business,name:task.value.business_name||'当前业务系统'},...props.businesses] : props.businesses)
async function changeType(value:string) {
  const previous = task.value.monitor_type
  if (value === previous) return
  if (task.value.id) {
    try { await ElMessageBox.confirm('切换类型将重置本次表单的协议参数，保存后生效。是否继续？','切换探测类型',{type:'warning',confirmButtonText:'切换类型',cancelButtonText:'保留原类型'}) } catch { return }
  } else {
    const previousDefaults = recommendations[previous] || recommendations.HTTP
    if (task.value.interval_seconds === previousDefaults[0]) task.value.interval_seconds = recommendations[value][0]
    if (task.value.timeout_seconds === previousDefaults[1]) task.value.timeout_seconds = recommendations[value][1]
  }
  task.value.monitor_type = value
}
function applyRecommendation() { [task.value.interval_seconds,task.value.timeout_seconds] = suggested.value }
function normalize() {
  if (!String(task.value.name||'').trim()) throw new Error('请填写任务名称')
  if (!task.value.business) throw new Error('请选择业务系统')
  if (!String(task.value.target||'').trim()) throw new Error('请填写探测目标')
  for (const [key,min,max,label] of [['interval_seconds',5,86400,'探测周期'],['timeout_seconds',1,30,'超时时间'],['failure_threshold',1,100,'失败确认次数'],['recovery_threshold',1,100,'恢复确认次数']] as const) {
    if (!Number.isInteger(task.value[key]) || task.value[key]<min || task.value[key]>max) throw new Error(`${label}必须为 ${min}～${max} 的整数`)
  }
  if (task.value.timeout_seconds >= task.value.interval_seconds) throw new Error('超时时间必须小于探测周期')
  const warning = task.value.warning_latency_ms
  if (warning != null && (!Number.isInteger(warning)||warning<0||warning>3600000)) throw new Error('响应预警阈值必须为 0～3600000 的整数')
  if (warning === undefined) task.value.warning_latency_ms = null
  return protocol.value!.normalize()
}
defineExpose({normalize})
</script>

<template>
 <el-form label-position="top" class="monitor-task-form" @submit.prevent>
  <div class="task-grid">
   <div class="section-title wide"><b>基础配置</b><el-tag size="small" effect="plain">{{task.monitor_type||'HTTP'}}</el-tag></div>
   <el-form-item label="任务名称" required><el-input v-model="task.name" placeholder="例如：订单服务可用性" maxlength="160"/></el-form-item>
   <el-form-item label="业务系统" required><el-select v-model="task.business" filterable placeholder="请选择业务系统"><el-option v-for="item in businessOptions" :key="item.id" :label="item.name" :value="item.id"/></el-select></el-form-item>
   <el-form-item label="探测类型" required><el-select :model-value="task.monitor_type" @update:model-value="changeType"><el-option v-for="type in types" :key="type" :value="type"/></el-select></el-form-item>
   <el-form-item label="任务状态"><div class="inline-control"><el-switch v-model="task.is_enabled"/><small>{{task.is_enabled?'启用，按周期自动执行':'暂停自动执行'}}</small></div></el-form-item>
   <el-form-item :label="['HTTP','API'].includes(task.monitor_type)?'接口地址':'探测目标'" class="wide" required><el-input v-model="task.target" :placeholder="hints[task.monitor_type]"/><small>{{['HTTP','API'].includes(task.monitor_type)?'填写完整 URL，支持路径与查询参数。':task.monitor_type==='DNS'?'只填写域名；解析服务器在下方配置。':task.monitor_type==='PING'?'填写 IP 或主机名，不需要协议和端口。':'填写主机或域名及端口；SSL 默认端口为 443。'}}</small></el-form-item>
   <el-form-item label="周期（秒）" required><el-input-number v-model="task.interval_seconds" :min="5" :max="86400" :precision="0" controls-position="right"/></el-form-item>
   <el-form-item label="超时（秒）" required><el-input-number v-model="task.timeout_seconds" :min="1" :max="30" :precision="0" controls-position="right"/></el-form-item>
   <div class="schedule-note wide"><span>每 {{task.interval_seconds}} 秒检查 · 超时 {{task.timeout_seconds}} 秒</span><el-button link type="primary" @click="applyRecommendation">应用 {{task.monitor_type}} 建议值（{{suggested[0]}} / {{suggested[1]}} 秒）</el-button></div>
  </div>
  <MonitorConfigFields ref="protocol" v-model="task.config" :type="task.monitor_type||'HTTP'" :editing="Boolean(task.id)"/>
  <el-collapse v-model="advanced" class="task-advanced"><el-collapse-item name="policy"><template #title>告警阈值与标签 <small>失败 {{task.failure_threshold}} 次 · 恢复 {{task.recovery_threshold}} 次</small></template>
   <div class="task-grid">
    <el-form-item label="连续失败阈值"><el-input-number v-model="task.failure_threshold" :min="1" :max="100" :precision="0" controls-position="right"/></el-form-item>
    <el-form-item label="连续恢复阈值"><el-input-number v-model="task.recovery_threshold" :min="1" :max="100" :precision="0" controls-position="right"/></el-form-item>
    <p class="wide help-note">首次失败会建立事件，达到失败阈值后标记故障；连续成功达到恢复阈值后确认恢复。通知渠道由关联的告警规则控制。</p>
    <el-form-item label="响应预警阈值（ms）"><el-input-number v-model="task.warning_latency_ms" :min="0" :max="3600000" :precision="0" controls-position="right" placeholder="留空不设置"/></el-form-item>
    <el-form-item label="标签"><el-select v-model="task.tags" multiple filterable clearable collapse-tags collapse-tags-tooltip :max-collapse-tags="2" placeholder="可选"><el-option v-for="item in tags" :key="item.id" :label="item.name" :value="item.id"/></el-select></el-form-item>
   </div>
  </el-collapse-item></el-collapse>
 </el-form>
</template>

<style scoped>
.task-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:0 20px}.wide{grid-column:1/-1}.section-title{display:flex;align-items:center;justify-content:space-between;margin:0 0 12px}.section-title b{font-size:14px}.monitor-task-form :deep(.el-form-item){margin-bottom:12px;min-width:0}.monitor-task-form :deep(.el-form-item__label){height:auto;line-height:20px;font-size:12px;margin-bottom:4px;padding:0;color:var(--text-secondary)}.monitor-task-form :deep(.el-input-number),.monitor-task-form :deep(.el-select){width:100%}.monitor-task-form :deep(.el-input-number .el-input__inner){text-align:left}.monitor-task-form small,.help-note{font-size:12px;line-height:1.5;color:var(--muted)}.el-form-item small{display:block;width:100%;margin-top:4px}.inline-control{display:flex;align-items:center;gap:10px;min-height:32px}.inline-control small{margin:0;width:auto}.schedule-note{display:flex;align-items:center;justify-content:space-between;gap:8px;flex-wrap:wrap;color:var(--muted);font-size:12px;margin:-2px 0 16px}.schedule-note .el-button{font-size:12px}.task-advanced{margin-top:8px}.task-advanced :deep(.el-collapse-item__header){font-size:13px;min-height:40px;height:auto;line-height:1.6;gap:8px;flex-wrap:wrap}.task-advanced :deep(.el-collapse-item__content){padding:12px 0 0}.help-note{margin:-2px 0 12px}@media(max-width:640px){.task-grid{grid-template-columns:minmax(0,1fr);gap:0}.schedule-note{align-items:flex-start;flex-direction:column}}
</style>
