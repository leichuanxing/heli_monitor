<script setup lang="ts">
import { computed, reactive, watch } from 'vue'

const props=defineProps<{type:string}>()
const config=defineModel<Record<string,any>>({default:()=>({})})
const databaseTypes=['MSSQL','POSTGRESQL','MYSQL','MONGODB']
const isDatabase=computed(()=>databaseTypes.includes(props.type))
const defaults:Record<string,Record<string,any>>={
  HTTP:{method:'GET',expected_status:[200],follow_redirects:true,verify_tls:true},
  API:{method:'GET',expected_status:[200],follow_redirects:true,verify_tls:true,auth:{type:'none'}},
  TCP:{send:'',expect:''},PING:{count:3},DNS:{record_type:'A',server:'',expected:[]},SSL:{warn_days:30},
  MSSQL:{database:'master',username:'',password:'',query:'SELECT 1',expected_value:1,tds_version:'7.4'},
  POSTGRESQL:{database:'postgres',username:'',password:'',query:'SELECT 1',expected_value:1,sslmode:'prefer'},
  MYSQL:{database:'mysql',username:'',password:'',query:'SELECT 1',expected_value:1,use_tls:false},
  MONGODB:{database:'admin',username:'',password:'',auth_source:'admin',use_tls:false},
}
const draft=reactive({statuses:'',keywords:'',dnsExpected:'',headers:'',params:'',body:''})
function syncDraft(){
  const statuses=config.value.expected_status
  const keywords=config.value.keywords
  const expected=config.value.expected
  draft.statuses=(Array.isArray(statuses)?statuses:statuses==null?[]:[statuses]).join(', ')
  draft.keywords=(Array.isArray(keywords)?keywords:keywords?String(keywords).split(','):[]).join(', ')
  draft.dnsExpected=(Array.isArray(expected)?expected:expected?[expected]:[]).join(', ')
  draft.headers=config.value.headers?JSON.stringify(config.value.headers,null,2):''
  draft.params=config.value.params?JSON.stringify(config.value.params,null,2):''
  const body=config.value.json??config.value.form
  draft.body=body===undefined?'':JSON.stringify(body,null,2)
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
  if(['HTTP','API'].includes(props.type)){
    const statuses=draft.statuses.split(',').map(x=>Number(x.trim())).filter(x=>Number.isInteger(x)&&x>=100&&x<=599)
    if(statuses.length)config.value.expected_status=statuses
    else delete config.value.expected_status
    config.value.keywords=draft.keywords.split(',').map(x=>x.trim()).filter(Boolean)
    for(const [key,value,label] of [['headers',draft.headers,'请求头'],['params',draft.params,'查询参数']] as const){const parsed=parseJson(value,label);if(parsed===undefined)delete config.value[key];else config.value[key]=parsed}
    if(props.type==='API'){const parsed=parseJson(draft.body,'请求体');delete config.value.json;delete config.value.form;if(parsed!==undefined)config.value.json=parsed}
  }
  if(props.type==='DNS')config.value.expected=draft.dnsExpected.split(',').map(x=>x.trim()).filter(Boolean)
  return config.value
}
defineExpose({normalize})
</script>

<template>
  <template v-if="isDatabase">
    <el-divider content-position="left">数据库连接参数</el-divider>
    <el-alert title="数据库地址在上方“目标”中填写，例如 10.0.0.11:5432" type="info" :closable="false" class="config-alert"/>
    <el-form-item label="数据库名称" required><el-input v-model="config.database" :placeholder="type==='MSSQL'?'例如：master':type==='MYSQL'?'例如：mysql':'例如：postgres / admin'"/></el-form-item>
    <el-form-item label="登录用户名" required><el-input v-model="config.username" placeholder="请输入数据库只读监控账号"/></el-form-item>
    <el-form-item label="登录密码" required><el-input v-model="config.password" type="password" show-password placeholder="编辑时保留 ******** 表示不修改"/></el-form-item>
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
    <el-form-item label="请求方法"><el-select v-model="config.method"><el-option v-for="v in ['GET','POST','PUT','PATCH','DELETE','HEAD']" :key="v" :value="v"/></el-select></el-form-item>
    <el-form-item label="期望状态码"><el-input v-model="draft.statuses" placeholder="多个状态码用逗号分隔，例如：200, 204"/></el-form-item>
    <el-form-item label="请求头 JSON"><el-input v-model="draft.headers" type="textarea" :rows="3" placeholder='例如：{"Accept":"application/json"}'/></el-form-item>
    <el-form-item label="查询参数 JSON"><el-input v-model="draft.params" type="textarea" :rows="3" placeholder='例如：{"region":"cn"}'/></el-form-item>
    <template v-if="type==='API'">
      <el-divider content-position="left">API 认证与请求体</el-divider>
      <el-form-item label="认证方式"><el-select v-model="authType"><el-option label="无认证" value="none"/><el-option label="Bearer Token" value="bearer"/><el-option label="Basic Auth" value="basic"/><el-option label="API Key" value="api_key"/><el-option label="OAuth2 客户端" value="oauth2_client_credentials"/></el-select></el-form-item>
      <el-form-item v-if="authType==='bearer'" label="Bearer Token"><el-input v-model="config.auth.token" type="password" show-password/></el-form-item>
      <template v-if="authType==='basic'"><el-form-item label="认证用户名"><el-input v-model="config.auth.username"/></el-form-item><el-form-item label="认证密码"><el-input v-model="config.auth.password" type="password" show-password/></el-form-item></template>
      <template v-if="authType==='api_key'"><el-form-item label="Key 名称"><el-input v-model="config.auth.name" placeholder="例如：X-API-Key"/></el-form-item><el-form-item label="Key 值"><el-input v-model="config.auth.value" type="password" show-password/></el-form-item><el-form-item label="传递位置"><el-select v-model="config.auth.in"><el-option label="请求头" value="header"/><el-option label="查询参数" value="query"/></el-select></el-form-item></template>
      <template v-if="authType==='oauth2_client_credentials'"><el-form-item label="Token URL"><el-input v-model="config.auth.token_url"/></el-form-item><el-form-item label="Client ID"><el-input v-model="config.auth.client_id"/></el-form-item><el-form-item label="Client Secret"><el-input v-model="config.auth.client_secret" type="password" show-password/></el-form-item></template>
      <el-form-item label="JSON 请求体"><el-input v-model="draft.body" type="textarea" :rows="4" placeholder='例如：{"ping":true}'/></el-form-item>
    </template>
    <el-divider content-position="left">响应验证</el-divider>
    <el-form-item label="包含关键字"><el-input v-model="draft.keywords" placeholder="多个关键字用逗号分隔"/></el-form-item>
    <el-form-item label="正则表达式"><el-input v-model="config.regex" placeholder="可选"/></el-form-item>
    <el-form-item label="跟随重定向"><el-switch v-model="config.follow_redirects"/></el-form-item>
    <el-form-item label="验证 TLS 证书"><el-switch v-model="config.verify_tls"/></el-form-item>
  </template>

  <template v-else-if="type==='TCP'"><el-divider content-position="left">TCP 协议验证</el-divider><el-form-item label="发送内容"><el-input v-model="config.send" type="textarea" :rows="3" placeholder="建立连接后发送的内容，可留空"/></el-form-item><el-form-item label="期望返回"><el-input v-model="config.expect" placeholder="返回内容应包含的文本，可留空"/></el-form-item></template>
  <template v-else-if="type==='PING'"><el-divider content-position="left">Ping 参数</el-divider><el-form-item label="发送次数"><el-input-number v-model="config.count" :min="1" :max="10"/></el-form-item></template>
  <template v-else-if="type==='DNS'"><el-divider content-position="left">DNS 查询参数</el-divider><el-form-item label="记录类型"><el-select v-model="config.record_type"><el-option v-for="v in ['A','AAAA','CNAME','MX','TXT']" :key="v" :value="v"/></el-select></el-form-item><el-form-item label="DNS 服务器"><el-input v-model="config.server" placeholder="可选，例如：8.8.8.8"/></el-form-item><el-form-item label="期望记录"><el-input v-model="draft.dnsExpected" placeholder="多个记录用逗号分隔；留空仅验证解析成功"/></el-form-item></template>
  <template v-else-if="type==='SSL'"><el-divider content-position="left">SSL 证书参数</el-divider><el-form-item label="到期预警天数"><el-input-number v-model="config.warn_days" :min="1" :max="3650"/></el-form-item></template>
</template>

<style scoped>.config-alert{margin:0 0 16px}.config-note{margin:0 0 18px 140px;color:#7f8da0;font-size:12px}.el-select{width:100%}</style>
