<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import ApiMonitorConfigFields from './ApiMonitorConfigFields.vue'
const props = defineProps<{type:string;editing?:boolean}>()
const config = defineModel<Record<string,any>>({default:()=>({})})
const web = computed(()=>['HTTP','API'].includes(props.type))
const isDatabase = computed(()=>['MSSQL','POSTGRESQL','MYSQL','MONGODB'].includes(props.type))
const apiFields = ref<InstanceType<typeof ApiMonitorConfigFields>>()
const advanced = ref<string[]>([])
const defaults:Record<string,Record<string,any>> = {
 HTTP:{method:'GET',follow_redirects:true,verify_tls:true,auth:{type:'none'}},API:{method:'GET',follow_redirects:true,verify_tls:true,auth:{type:'none'}},
 TCP:{send:'',expect:'',send_escapes:true,receive_bytes:4096},PING:{count:3,max_packet_loss:0},DNS:{record_type:'A',server:'',expected:[]},SSL:{warn_days:30,expiry_action:'notify'},
 MSSQL:{database:'master',username:'',password:'',query:'SELECT 1',expected_value:1,tds_version:'7.4'},POSTGRESQL:{database:'postgres',username:'',password:'',query:'SELECT 1',expected_value:1,sslmode:'prefer'},MYSQL:{database:'',username:'',password:'',query:'SELECT 1',expected_value:1,use_tls:false},MONGODB:{auth_enabled:true,database:'admin',username:'',password:'',auth_source:'admin',use_tls:false},
}
const draft = reactive({dnsExpected:''})
function syncDraft(){draft.dnsExpected=(config.value.expected||[]).join(', ')}
function fillDefaults(type:string){
 const existing=props.editing||Object.keys(config.value).length>0
 for(const [key,value] of Object.entries(defaults[type]||{})){
  if(existing&&['expected_value','expiry_action'].includes(key))continue
  if(config.value[key]===undefined)config.value[key]=structuredClone(value)
 }
}
watch(()=>props.type,(type,old)=>{
 if(old&&old!==type){config.value=structuredClone(defaults[type]||{});advanced.value=[]}else fillDefaults(type)
 syncDraft()
},{immediate:true})
watch(()=>config.value,()=>{fillDefaults(props.type);syncDraft()})
function normalize(){
 if(web.value){if(!apiFields.value)throw new Error('请求配置尚未加载');return apiFields.value.normalize()}
 const value={...config.value}
 if(props.type==='DNS')value.expected=draft.dnsExpected.split(/[,，]/).map(item=>item.trim()).filter(Boolean)
 if(isDatabase.value){
  if(!String(value.database||'').trim())throw new Error('请填写数据库名称')
  if((props.type!=='MONGODB'||value.auth_enabled!==false)&&(!String(value.username||'').trim()||!value.password))throw new Error('请填写数据库用户名和密码')
  if(props.type!=='MONGODB'&&!String(value.query||'').trim())throw new Error('请填写只读查询语句')
  if(value.expected_value==='')delete value.expected_value
 }
 config.value=value
 return value
}
defineExpose({normalize})
</script>
<template>
 <section class="probe-settings">
  <ApiMonitorConfigFields v-if="web" ref="apiFields" v-model="config" :body-label="type==='HTTP'?'请求体类型':'发送内容'"/>
  <div v-else class="protocol-grid">
   <div class="protocol-title wide">{{isDatabase?'数据库连接':type==='SSL'?'证书检查':type==='DNS'?'域名解析':type==='TCP'?'端口与协议检查':'Ping 检查'}}</div>
   <template v-if="isDatabase">
    <el-form-item label="数据库名称" required><el-input v-model="config.database" :placeholder="type==='MYSQL'?'填写需要监控的业务数据库':'例如：postgres / master / admin'"/></el-form-item>
    <el-form-item v-if="type==='MONGODB'" label="启用认证"><el-switch v-model="config.auth_enabled"/></el-form-item>
    <el-form-item v-if="type!=='MONGODB'||config.auth_enabled!==false" label="登录用户名" required><el-input v-model="config.username" placeholder="建议使用只读监控账号"/></el-form-item>
    <el-form-item v-if="type!=='MONGODB'||config.auth_enabled!==false" label="登录密码" required><el-input v-model="config.password" type="password" show-password placeholder="保留 ******** 表示不修改"/></el-form-item>
    <template v-if="type!=='MONGODB'">
     <el-form-item label="只读查询语句" class="wide" required><el-input v-model="config.query" type="textarea" :rows="2" placeholder="SELECT 1；仅支持 SELECT / WITH 只读查询"/></el-form-item>
     <el-form-item label="期望结果" class="wide"><el-input v-model="config.expected_value" placeholder="可选，例如 1；留空只检查查询是否成功"/></el-form-item>
    </template>
    <p v-else class="help wide">使用 MongoDB ping 命令检查连接及认证，无需填写 SQL。</p>
    <el-collapse v-model="advanced" class="wide"><el-collapse-item name="connection" title="连接高级设置（TLS / 协议）"><div class="protocol-grid">
     <el-form-item v-if="type==='POSTGRESQL'" label="SSL 模式"><el-select v-model="config.sslmode"><el-option v-for="value in ['disable','allow','prefer','require','verify-ca','verify-full']" :key="value" :value="value"/></el-select></el-form-item>
     <el-form-item v-if="type==='MSSQL'" label="TDS 版本"><el-select v-model="config.tds_version"><el-option v-for="value in ['7.1','7.2','7.3','7.4']" :key="value" :value="value"/></el-select></el-form-item>
     <el-form-item v-if="type==='MYSQL'||type==='MONGODB'" label="TLS 加密"><el-switch v-model="config.use_tls"/></el-form-item>
     <el-form-item v-if="type==='MONGODB'&&config.auth_enabled!==false" label="认证数据库"><el-input v-model="config.auth_source" placeholder="通常为 admin"/></el-form-item>
    </div></el-collapse-item></el-collapse>
   </template>
   <template v-else-if="type==='TCP'">
    <el-form-item label="发送内容" class="wide"><el-input v-model="config.send" type="textarea" :rows="2" placeholder="可选；连接后发送的内容"/></el-form-item>
    <el-form-item label="期望返回" class="wide"><el-input v-model="config.expect" placeholder="可选；检查返回内容包含此文本"/></el-form-item>
    <p class="help wide">两项均留空时只验证端口能否建立连接。</p>
    <el-collapse v-model="advanced" class="wide"><el-collapse-item name="tcp" title="收发高级设置"><div class="protocol-grid">
     <el-form-item label="解析转义字符"><el-switch v-model="config.send_escapes"/><small>将 \r\n 转为换行，关闭则按原样发送。</small></el-form-item>
     <el-form-item label="最大读取字节"><el-input-number v-model="config.receive_bytes" :min="256" :max="65536" :precision="0" controls-position="right"/></el-form-item>
    </div></el-collapse-item></el-collapse>
   </template>
   <template v-else-if="type==='PING'">
    <el-form-item label="发送次数"><el-input-number v-model="config.count" :min="1" :max="10" :precision="0" controls-position="right"/></el-form-item>
    <el-form-item label="允许丢包率（%）"><el-input-number v-model="config.max_packet_loss" :min="0" :max="99" controls-position="right"/></el-form-item>
    <p class="help wide">默认发送 3 次、允许丢包率 0%；超过设置的丢包率即判定失败。</p>
   </template>
   <template v-else-if="type==='DNS'">
    <el-form-item label="记录类型"><el-select v-model="config.record_type"><el-option v-for="value in ['A','AAAA','CNAME','MX','TXT','NS','SRV']" :key="value" :value="value"/></el-select></el-form-item>
    <el-form-item label="DNS 服务器"><el-input v-model="config.server" placeholder="留空使用系统 DNS；填写服务器 IP"/></el-form-item>
    <el-form-item label="期望记录" class="wide"><el-input v-model="draft.dnsExpected" placeholder="可选；多条记录以逗号分隔"/><small>留空只验证解析成功；填写时检查返回记录包含配置内容。</small></el-form-item>
   </template>
   <template v-else-if="type==='SSL'">
    <el-form-item label="提前提醒天数"><el-input-number v-model="config.warn_days" :min="1" :max="3650" :precision="0" controls-position="right"/></el-form-item>
    <el-form-item label="进入提醒期时"><el-select v-model="config.expiry_action" placeholder="未单独设置：仅页面预警"><el-option label="提前通知，服务仍可用" value="notify"/><el-option label="仅页面预警" value="warn"/><el-option label="按探测失败处理" value="fail"/></el-select></el-form-item>
    <p class="help wide">通知需关联已启用的告警规则及通知渠道。到期时间和有效期天数在历史数据中展示。</p>
   </template>
  </div>
 </section>
</template>
<style scoped>
.probe-settings{min-width:0;border-top:1px solid var(--divider);padding-top:14px}.protocol-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:0 20px}.wide{grid-column:1/-1}.protocol-title{font-size:14px;font-weight:600;margin-bottom:12px}.help,small{font-size:12px;line-height:1.5;color:var(--muted)}.help{margin:0 0 12px}small{display:block;width:100%;margin-top:4px}.el-select,.el-input-number{width:100%}.el-collapse :deep(.el-collapse-item__header){min-height:38px;height:auto;font-size:13px;line-height:1.6}.el-collapse :deep(.el-collapse-item__content){padding:12px 0 0}@media(max-width:640px){.protocol-grid{grid-template-columns:minmax(0,1fr);gap:0}}
</style>
