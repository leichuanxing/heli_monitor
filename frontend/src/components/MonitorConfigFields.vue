<script setup lang="ts">
import { computed, reactive, watch } from 'vue'

const props=defineProps<{type:string}>()
const config=defineModel<Record<string,any>>({default:()=>({})})
const databaseTypes=['MSSQL','POSTGRESQL','MYSQL','MONGODB']
const isDatabase=computed(()=>databaseTypes.includes(props.type))
const defaults:Record<string,Record<string,any>>={
  HTTP:{method:'GET',follow_redirects:true,verify_tls:true,auth:{type:'none'}},
  API:{method:'GET',follow_redirects:true,verify_tls:true,auth:{type:'none'}},
  TCP:{send:'',expect:'',send_escapes:true,receive_bytes:4096},PING:{count:3,max_packet_loss:0},DNS:{record_type:'A',server:'',expected:[]},SSL:{warn_days:30,expiry_action:'warn'},
  MSSQL:{database:'master',username:'',password:'',query:'SELECT 1',expected_value:1,tds_version:'7.4'},
  POSTGRESQL:{database:'postgres',username:'',password:'',query:'SELECT 1',expected_value:1,sslmode:'prefer'},
  MYSQL:{database:'mysql',username:'',password:'',query:'SELECT 1',expected_value:1,use_tls:false},
  MONGODB:{auth_enabled:true,database:'admin',username:'',password:'',auth_source:'admin',use_tls:false},
}
const draft=reactive({statuses:'',keywords:'',dnsExpected:'',headers:'',params:'',body:'',bodyType:'none',assertions:''})
function syncDraft(){
  const statuses=config.value.expected_status
  const keywords=config.value.keywords
  const expected=config.value.expected
  draft.statuses=(Array.isArray(statuses)?statuses:statuses==null?[]:[statuses]).join(', ')
  draft.keywords=(Array.isArray(keywords)?keywords:keywords?String(keywords).split(','):[]).join(', ')
  draft.dnsExpected=(Array.isArray(expected)?expected:expected?[expected]:[]).join(', ')
  draft.headers=config.value.headers?JSON.stringify(config.value.headers,null,2):''
  draft.params=config.value.params?JSON.stringify(config.value.params,null,2):''
  draft.bodyType=config.value.json!==undefined?'json':config.value.form!==undefined?'form':config.value.body!==undefined?'text':'none'
  draft.body=draft.bodyType==='text'?String(config.value.body):draft.bodyType==='none'?'':JSON.stringify(config.value[draft.bodyType],null,2)
  draft.assertions=config.value.json_assertions?JSON.stringify(config.value.json_assertions,null,2):''
}
watch(()=>props.type,(type,old)=>{
  if(old&&old!==type||!Object.keys(config.value||{}).length)config.value=structuredClone(defaults[type]||{})
  syncDraft()
},{immediate:true})
// 编辑同一类型的另一条任务时 type 不会变化，但 v-model 对象会被替换。
watch(()=>config.value,()=>syncDraft())
const authType=computed({get:()=>config.value.auth?.type||'none',set:value=>{config.value.auth={type:value}}})
function parseJson(value:string,label:string){try{return value.trim()?JSON.parse(value):undefined}catch{throw new Error(`${label}必须是合法 JSON`)}}
function normalize(){
  const value={...config.value}
  if(['HTTP','API'].includes(props.type)){
    const parts=draft.statuses.trim()?draft.statuses.split(/[,，]/).map(x=>x.trim()):[]
    if(parts.some(x=>!/^\d{3}$/.test(x)||Number(x)<100||Number(x)>599))throw new Error('期望状态码必须为 100 到 599，多个值用逗号分隔')
    if(parts.length)value.expected_status=[...new Set(parts.map(Number))]
    else delete value.expected_status
    value.keywords=draft.keywords.split(/[,，]/).map(x=>x.trim()).filter(Boolean)
    for(const [key,text,label] of [['headers',draft.headers,'请求头'],['params',draft.params,'查询参数']] as const){
      const parsed=parseJson(text,label)
      if(parsed!==undefined&&(typeof parsed!=='object'||parsed===null||Array.isArray(parsed)))throw new Error(`${label}必须是 JSON 对象`)
      if(parsed===undefined)delete value[key];else value[key]=parsed
    }
    delete value.json;delete value.form;delete value.body
    if(draft.bodyType==='text')value.body=draft.body
    else if(draft.bodyType==='json'||draft.bodyType==='form'){
      const parsed=parseJson(draft.body,'请求体')
      if(parsed===undefined)throw new Error('请填写请求体，或将请求体类型改为无')
      if(draft.bodyType==='form'&&(typeof parsed!=='object'||parsed===null||Array.isArray(parsed)))throw new Error('表单请求体必须是 JSON 对象')
      value[draft.bodyType]=parsed
    }
    const assertions=parseJson(draft.assertions,'JSON 断言')
    if(assertions!==undefined&&!Array.isArray(assertions))throw new Error('JSON 断言必须为数组')
    if(assertions===undefined)delete value.json_assertions;else value.json_assertions=assertions
  }
  if(props.type==='DNS')value.expected=draft.dnsExpected.split(/[,，]/).map(x=>x.trim()).filter(Boolean)
  if(isDatabase.value&&value.expected_value==='')delete value.expected_value
  config.value=value
  return value
}

defineExpose({normalize})
</script>

<template>
  <template v-if="isDatabase">
    <el-divider content-position="left">数据库连接参数</el-divider>
    <el-alert title="数据库地址在上方“目标”中填写，例如 10.0.0.11:5432" type="info" :closable="false" class="config-alert"/>
    <el-form-item v-if="type==='MONGODB'" label="启用认证"><el-switch v-model="config.auth_enabled"/></el-form-item>
    <el-form-item label="数据库名称" required><el-input v-model="config.database" :placeholder="type==='MSSQL'?'例如：master':type==='MYSQL'?'例如：mysql':'例如：postgres / admin'"/></el-form-item>
    <el-form-item v-if="type!=='MONGODB'||config.auth_enabled!==false" label="登录用户名" required><el-input v-model="config.username" placeholder="请输入数据库只读监控账号"/></el-form-item>
    <el-form-item v-if="type!=='MONGODB'||config.auth_enabled!==false" label="登录密码" required><el-input v-model="config.password" type="password" show-password placeholder="编辑时保留 ******** 表示不修改"/></el-form-item>
    <el-form-item v-if="type==='POSTGRESQL'" label="SSL 模式"><el-select v-model="config.sslmode"><el-option v-for="v in ['disable','allow','prefer','require','verify-ca','verify-full']" :key="v" :value="v"/></el-select></el-form-item>
    <el-form-item v-if="type==='MSSQL'" label="TDS 版本"><el-select v-model="config.tds_version"><el-option v-for="v in ['7.1','7.2','7.3','7.4']" :key="v" :value="v"/></el-select></el-form-item>
    <el-form-item v-if="type==='MYSQL'||type==='MONGODB'" label="TLS 加密"><el-switch v-model="config.use_tls"/></el-form-item>
    <el-form-item v-if="type==='MONGODB'" label="认证数据库"><el-input v-model="config.auth_source" placeholder="通常为 admin"/></el-form-item>
    <el-divider content-position="left">查询语句与结果验证</el-divider>
    <template v-if="type!=='MONGODB'">
      <el-form-item label="查询语句" required><el-input v-model="config.query" type="textarea" :rows="4" placeholder="只允许 SELECT 或 WITH 查询，例如：SELECT 1"/></el-form-item>
      <el-form-item label="期望结果"><el-input v-model="config.expected_value" placeholder="例如：1；留空表示查询成功即判定可用"/></el-form-item>
    </template>
    <el-alert v-else title="MongoDB 使用数据库 ping 命令验证服务及认证是否可用" type="success" :closable="false" class="config-alert"/>
    <p class="config-note">探测结果会分别记录数据库连接耗时、查询耗时和总响应时间。</p>
  </template>

  <template v-else-if="type==='HTTP'||type==='API'">
    <el-divider content-position="left">HTTP 请求参数</el-divider>
    <el-form-item label="请求方法"><el-select v-model="config.method"><el-option v-for="v in ['GET','POST','PUT','PATCH','DELETE','HEAD','OPTIONS']" :key="v" :value="v"/></el-select></el-form-item>
    <el-form-item label="期望状态码"><el-input v-model="draft.statuses" placeholder="留空接受全部 2xx；例如：200, 204"/></el-form-item>
    <el-form-item label="请求头 JSON"><el-input v-model="draft.headers" type="textarea" :rows="3" placeholder='例如：{"Accept":"application/json"}'/></el-form-item>
    <el-form-item label="查询参数 JSON"><el-input v-model="draft.params" type="textarea" :rows="3" placeholder='例如：{"region":"cn"}'/></el-form-item>
    <template v-if="type==='HTTP'||type==='API'">
      <el-divider content-position="left">认证与请求体</el-divider>
      <el-form-item label="认证方式"><el-select v-model="authType"><el-option label="无认证" value="none"/><el-option label="Bearer Token" value="bearer"/><el-option label="Basic Auth" value="basic"/><el-option label="API Key" value="api_key"/><el-option label="OAuth2 客户端" value="oauth2_client_credentials"/></el-select></el-form-item>
      <el-form-item v-if="authType==='bearer'" label="Bearer Token"><el-input v-model="config.auth.token" type="password" show-password/></el-form-item>
      <template v-if="authType==='basic'"><el-form-item label="认证用户名"><el-input v-model="config.auth.username"/></el-form-item><el-form-item label="认证密码"><el-input v-model="config.auth.password" type="password" show-password/></el-form-item></template>
      <template v-if="authType==='api_key'"><el-form-item label="Key 名称"><el-input v-model="config.auth.name" placeholder="例如：X-API-Key"/></el-form-item><el-form-item label="Key 值"><el-input v-model="config.auth.value" type="password" show-password/></el-form-item><el-form-item label="传递位置"><el-select v-model="config.auth.in"><el-option label="请求头" value="header"/><el-option label="查询参数" value="query"/></el-select></el-form-item></template>
      <template v-if="authType==='oauth2_client_credentials'"><el-form-item label="Token URL"><el-input v-model="config.auth.token_url"/></el-form-item><el-form-item label="Client ID"><el-input v-model="config.auth.client_id"/></el-form-item><el-form-item label="Client Secret"><el-input v-model="config.auth.client_secret" type="password" show-password/></el-form-item></template>
      <el-form-item label="请求体类型"><el-select v-model="draft.bodyType"><el-option label="无请求体" value="none"/><el-option label="JSON" value="json"/><el-option label="表单（JSON 对象）" value="form"/><el-option label="原始文本" value="text"/></el-select></el-form-item>
      <el-form-item v-if="draft.bodyType!=='none'" label="请求体"><el-input v-model="draft.body" type="textarea" :rows="4" :placeholder="draft.bodyType==='text'?'按原样发送文本':'例如：{&quot;ping&quot;:true}'"/></el-form-item>
    </template>
    <el-divider content-position="left">响应验证</el-divider>
    <el-form-item label="包含关键字"><el-input v-model="draft.keywords" placeholder="多个关键字用逗号分隔"/></el-form-item>
    <el-form-item label="正则表达式"><el-input v-model="config.regex" placeholder="可选"/></el-form-item>
    <el-form-item label="JSON 断言"><el-input v-model="draft.assertions" type="textarea" :rows="3" placeholder='例如：[{"path":"$.status","value":"ok"}]；不填写 value 时只验证路径存在'/></el-form-item>
    <el-form-item label="跟随重定向"><el-switch v-model="config.follow_redirects"/></el-form-item>
    <el-form-item label="验证 TLS 证书"><el-switch v-model="config.verify_tls"/></el-form-item>
  </template>

  <template v-else-if="type==='TCP'"><el-divider content-position="left">TCP 协议验证</el-divider><el-form-item label="解析转义字符"><el-switch v-model="config.send_escapes"/><small>启用时将 \r\n 转为换行；关闭则按原样发送</small></el-form-item><el-form-item label="发送内容"><el-input v-model="config.send" type="textarea" :rows="3" placeholder="建立连接后发送的内容，可留空"/></el-form-item><el-form-item label="期望返回"><el-input v-model="config.expect" placeholder="返回内容应包含的文本，可留空"/></el-form-item></template>
  <template v-else-if="type==='PING'"><el-divider content-position="left">Ping 参数</el-divider><el-form-item label="允许丢包率(%)"><el-input-number v-model="config.max_packet_loss" :min="0" :max="99"/></el-form-item><el-form-item label="发送次数"><el-input-number v-model="config.count" :min="1" :max="10"/></el-form-item></template>
  <template v-else-if="type==='DNS'"><el-divider content-position="left">DNS 查询参数</el-divider><el-form-item label="记录类型"><el-select v-model="config.record_type"><el-option v-for="v in ['A','AAAA','CNAME','MX','TXT','NS','SRV']" :key="v" :value="v"/></el-select></el-form-item><el-form-item label="DNS 服务器"><el-input v-model="config.server" placeholder="可选，例如：8.8.8.8"/></el-form-item><el-form-item label="期望记录"><el-input v-model="draft.dnsExpected" placeholder="多个记录用逗号分隔；留空仅验证解析成功"/></el-form-item></template>
  <template v-else-if="type==='SSL'"><el-divider content-position="left">SSL 证书参数</el-divider><el-form-item label="进入预警期时"><el-select v-model="config.expiry_action"><el-option label="状态降级（仅提示，不触发故障通知）" value="warn"/><el-option label="探测失败（按关联告警规则通知）" value="fail"/></el-select></el-form-item><el-form-item label="到期预警天数"><el-input-number v-model="config.warn_days" :min="1" :max="3650"/></el-form-item></template>
</template>

<style scoped>.config-alert{margin:0 0 16px}.config-note{margin:0 0 18px 140px;color:#7f8da0;font-size:12px}.el-select{width:100%}</style>
