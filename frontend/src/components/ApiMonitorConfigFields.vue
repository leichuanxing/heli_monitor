<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import RequestFieldRows from './RequestFieldRows.vue'
import { fieldRows, fieldsObject, isTextObject, type RequestField } from './requestFields'

withDefaults(defineProps<{bodyLabel?:string}>(), {bodyLabel:'发送内容'})
const config = defineModel<Record<string, any>>({ required: true })
const draft = reactive({ statuses: '', keywords: '', params: '', body: '', bodyType: 'none', assertions: '' })
const headers = ref<RequestField[]>([]), params = ref<RequestField[]>([]), body = ref<RequestField[]>([])
const paramsMode = ref('pairs'), bodyMode = ref('pairs'), advanced = ref<string[]>([]), editorError = ref('')
const initialParams = ref(false)
let syncing = false, syncedMethod = ''
const authType = computed({ get: () => config.value.auth?.type || 'none', set: value => { config.value.auth = value === 'api_key' ? { type: value, in: 'header' } : { type: value } } })
const queryInBasic = computed(() => initialParams.value)
const advancedCount = computed(() => [
  headers.value.some(row => row.name.trim()), draft.statuses.trim(), draft.keywords.trim(),
  config.value.regex, draft.assertions.trim(), config.value.verify_tls === false,
  config.value.follow_redirects === false,
  !queryInBasic.value && (paramsMode.value === 'pairs' ? params.value.some(row => row.name.trim()) : draft.params.trim()),
].filter(Boolean).length)
const summary = computed(() => draft.statuses.trim() ? `成功状态码：${draft.statuses}` : '默认接受全部 2xx（包含 200、201）')
function sync() {
  syncing = true
  const value = config.value
  syncedMethod = value.method
  draft.statuses = (Array.isArray(value.expected_status) ? value.expected_status : value.expected_status == null ? [] : [value.expected_status]).join(', ')
  draft.keywords = (Array.isArray(value.keywords) ? value.keywords : value.keywords ? [value.keywords] : []).join(', ')
  headers.value = fieldRows(value.headers)
  initialParams.value = !!value.params && Object.keys(value.params).length > 0
  draft.params = value.params ? JSON.stringify(value.params, null, 2) : ''
  paramsMode.value = !value.params || isTextObject(value.params) ? 'pairs' : 'raw'
  params.value = fieldRows(isTextObject(value.params) ? value.params : undefined)
  draft.bodyType = value.json !== undefined ? 'json' : value.form !== undefined ? 'form' : value.body !== undefined ? 'text' : 'none'
  const content = draft.bodyType === 'json' ? value.json : value.form
  draft.body = draft.bodyType === 'text' ? String(value.body) : draft.bodyType === 'none' ? '' : JSON.stringify(content, null, 2)
  bodyMode.value = content === undefined || isTextObject(content) ? 'pairs' : 'raw'
  body.value = fieldRows(isTextObject(content) ? content : undefined)
  draft.assertions = value.json_assertions ? JSON.stringify(value.json_assertions, null, 2) : ''
  editorError.value = ''
  syncing = false
}
watch(() => config.value, sync, { immediate: true })
watch(() => config.value.method, (method, previous) => {
  if (method === syncedMethod) return
  if (previous && method !== previous && ['POST', 'PUT', 'PATCH'].includes(method) && draft.bodyType === 'none') draft.bodyType = 'json'
})
watch(() => draft.bodyType, (type, previous) => {
  if (syncing) return
  editorError.value = ''
  if (type === 'text' && ['json', 'form'].includes(previous) && bodyMode.value === 'pairs') {
    try { draft.body = JSON.stringify(fieldsObject(body.value, '请求参数'), null, 2) }
    catch (error) {
      syncing = true; draft.bodyType = previous; syncing = false
      editorError.value = (error as Error).message
    }
  } else if (previous === 'text' && ['json', 'form'].includes(type)) {
    const parsed = (() => { try { return JSON.parse(draft.body) } catch { return undefined } })()
    bodyMode.value = isTextObject(parsed) ? 'pairs' : 'raw'
    if (isTextObject(parsed)) body.value = fieldRows(parsed)
  }
}, { flush: 'sync' })
function json(text: string, label: string): any {
  try { return text.trim() ? JSON.parse(text) : undefined } catch { throw new Error(`${label}必须是合法 JSON`) }
}
function toggleEditor(target: 'params' | 'body') {
  const mode = target === 'params' ? paramsMode : bodyMode
  const rows = target === 'params' ? params : body
  const label = target === 'params' ? '查询参数' : '请求内容'
  try {
    if (mode.value === 'pairs') { draft[target] = JSON.stringify(fieldsObject(rows.value, label), null, 2); mode.value = 'raw' }
    else {
      const parsed = json(draft[target], label) ?? {}
      if (!isTextObject(parsed)) throw new Error('包含数字、布尔值、数组或嵌套对象的 JSON 请保留文本编辑，以免改变数据类型')
      rows.value = fieldRows(parsed); mode.value = 'pairs'
    }
    editorError.value = ''
  } catch (error) { editorError.value = (error as Error).message }
}
function normalize() {
  const value = { ...config.value }
  const statuses = draft.statuses.trim() ? draft.statuses.split(/[,，]/).map(item => item.trim()) : []
  if (statuses.some(item => !/^\d{3}$/.test(item) || Number(item) < 100 || Number(item) > 599)) throw new Error('期望状态码必须为 100 到 599，多个值用逗号分隔')
  if (statuses.length) value.expected_status = [...new Set(statuses.map(Number))]
  else delete value.expected_status
  value.keywords = draft.keywords.split(/[,，]/).map(item => item.trim()).filter(Boolean)
  const headerValues = fieldsObject(headers.value, '请求头', true)
  // Header names are case-insensitive; never silently send duplicates.
  const headerNames = Object.keys(headerValues).map(name => name.toLowerCase())
  if (new Set(headerNames).size !== headerNames.length) throw new Error('请求头名称不能重复（不区分大小写）')
  if (Object.keys(headerValues).length) value.headers = headerValues
  else delete value.headers
  const query = paramsMode.value === 'pairs' ? fieldsObject(params.value, '查询参数') : json(draft.params, '查询参数')
  if (query !== undefined && (query === null || typeof query !== 'object' || Array.isArray(query))) throw new Error('查询参数必须是 JSON 对象')
  if (query && Object.keys(query).length) value.params = query
  else delete value.params
  delete value.json; delete value.form; delete value.body
  if (draft.bodyType === 'text') value.body = draft.body
  else if (['json', 'form'].includes(draft.bodyType)) {
    const content = bodyMode.value === 'pairs' ? fieldsObject(body.value, '请求参数') : json(draft.body, '请求内容')
    if (content === undefined) throw new Error('请填写请求内容，或将发送内容改为无')
    if (draft.bodyType === 'form' && (content === null || typeof content !== 'object' || Array.isArray(content))) throw new Error('表单请求体必须是 JSON 对象')
    value[draft.bodyType] = content
  }
  const assertions = json(draft.assertions, 'JSON 断言')
  if (assertions !== undefined && !Array.isArray(assertions)) throw new Error('JSON 断言必须为数组')
  if (assertions === undefined) delete value.json_assertions
  else value.json_assertions = assertions
  config.value = value
  return value
}
defineExpose({ normalize })
</script>

<template>
  <section class="api-request" aria-label="API 请求配置">
    <el-divider content-position="left">接口请求</el-divider>
    <el-form-item label="请求方法" class="api-half"><el-select v-model="config.method"><el-option v-for="method in ['GET','POST','PUT','PATCH','DELETE','HEAD','OPTIONS']" :key="method" :value="method"/></el-select></el-form-item>
    <el-form-item label="认证方式" class="api-half"><el-select v-model="authType"><el-option label="无需额外认证" value="none"/><el-option label="Bearer Token" value="bearer"/><el-option label="用户名 / 密码（Basic）" value="basic"/><el-option label="API Key" value="api_key"/><el-option label="OAuth2 客户端" value="oauth2_client_credentials"/></el-select></el-form-item>
    <el-form-item v-if="authType==='bearer'" label="Token"><el-input v-model="config.auth.token" type="password" show-password placeholder="填写 Token，无需添加 Bearer 前缀"/></el-form-item>
    <template v-if="authType==='basic'"><el-form-item label="认证用户名" class="api-half"><el-input v-model="config.auth.username"/></el-form-item><el-form-item label="认证密码" class="api-half"><el-input v-model="config.auth.password" type="password" show-password/></el-form-item></template>
    <template v-if="authType==='api_key'"><el-form-item label="Key 名称" class="api-half"><el-input v-model="config.auth.name" placeholder="例如：X-API-Key"/></el-form-item><el-form-item label="Key 值" class="api-half"><el-input v-model="config.auth.value" type="password" show-password/></el-form-item><el-form-item label="传递位置"><el-select v-model="config.auth.in"><el-option label="请求头" value="header"/><el-option label="查询参数" value="query"/></el-select></el-form-item></template>
    <template v-if="authType==='oauth2_client_credentials'"><el-form-item label="Token URL"><el-input v-model="config.auth.token_url"/></el-form-item><el-form-item label="Client ID" class="api-half"><el-input v-model="config.auth.client_id"/></el-form-item><el-form-item label="Client Secret" class="api-half"><el-input v-model="config.auth.client_secret" type="password" show-password/></el-form-item></template>
    <el-form-item v-if="queryInBasic" label="查询参数">
      <div class="editor"><RequestFieldRows v-if="paramsMode==='pairs'" v-model="params" label="查询参数"/><el-input v-else v-model="draft.params" type="textarea" :rows="3" aria-label="查询参数 JSON"/><el-button link @click="toggleEditor('params')">{{paramsMode==='pairs'?'使用 JSON 文本':'使用参数名 / 值'}}</el-button></div>
    </el-form-item>
    <el-form-item :label="bodyLabel"><el-select v-model="draft.bodyType"><el-option label="无请求体" value="none"/><el-option label="JSON（常用）" value="json"/><el-option label="表单" value="form"/><el-option label="原始文本" value="text"/></el-select></el-form-item>
    <el-form-item v-if="draft.bodyType!=='none'" label="请求参数">
      <div class="editor"><RequestFieldRows v-if="draft.bodyType!=='text'&&bodyMode==='pairs'" v-model="body" label="请求参数"/><el-input v-else v-model="draft.body" type="textarea" :rows="3" aria-label="请求内容文本" placeholder="保留 JSON 数据类型，也可发送原始文本"/><el-button v-if="draft.bodyType!=='text'" link @click="toggleEditor('body')">{{bodyMode==='pairs'?'使用 JSON 文本':'使用参数名 / 值'}}</el-button><small>登录接口可选择 POST，再填写 username、password；JSON 和表单会自动设置内容类型。</small></div>
    </el-form-item>
    <p v-if="editorError" role="alert" class="editor-error">{{editorError}}</p>
    <p class="request-summary">{{summary}}<span v-if="config.verify_tls===false"> · 当前未校验 TLS 证书</span></p>
    <el-collapse v-model="advanced" class="api-advanced">
      <el-collapse-item name="request"><template #title>高级设置（请求头、查询参数、响应校验、TLS）<span v-if="advancedCount" class="configured">已配置 {{advancedCount}} 项</span></template>
        <el-form-item label="请求头"><RequestFieldRows v-model="headers" label="请求头"/></el-form-item>
        <el-form-item v-if="!queryInBasic" label="查询参数"><div class="editor"><RequestFieldRows v-if="paramsMode==='pairs'" v-model="params" label="查询参数"/><el-input v-else v-model="draft.params" type="textarea" :rows="3" aria-label="查询参数 JSON"/><el-button link @click="toggleEditor('params')">{{paramsMode==='pairs'?'使用 JSON 文本':'使用参数名 / 值'}}</el-button></div></el-form-item>
        <el-form-item label="期望状态码"><el-input v-model="draft.statuses" placeholder="留空接受全部 2xx；可填写 200, 201"/></el-form-item>
        <el-form-item label="包含关键字"><el-input v-model="draft.keywords" placeholder="可选，多个关键字用逗号分隔"/></el-form-item>
        <el-form-item label="正则表达式"><el-input v-model="config.regex" placeholder="可选"/></el-form-item>
        <el-form-item label="JSON 断言"><el-input v-model="draft.assertions" type="textarea" :rows="3" placeholder='例如：[{"path":"$.status","value":"ok"}]'/></el-form-item>
        <el-form-item label="跟随重定向"><el-switch v-model="config.follow_redirects"/></el-form-item>
        <el-form-item label="验证 TLS 证书"><el-switch v-model="config.verify_tls"/></el-form-item>
      </el-collapse-item>
    </el-collapse>
  </section>
</template>

<style scoped>
.api-request{min-width:0;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));column-gap:16px}.api-request>*{grid-column:1/-1}.api-request>.api-half{grid-column:auto}.el-select,.editor{width:100%}.editor>small{display:block;line-height:1.6;color:var(--muted);margin-top:6px}.editor>.el-button{margin-top:6px}.request-summary{margin:0 0 10px;color:var(--text-secondary);font-size:12px;line-height:1.7}.editor-error{margin-left:0;color:var(--el-color-danger);font-size:12px}.configured{margin-left:10px;color:var(--brand);font-size:12px}.api-advanced{margin:8px 0 16px}.api-advanced :deep(.el-collapse-item__header){height:auto;min-height:44px;line-height:1.6;flex-wrap:wrap;padding:8px 0}.api-advanced :deep(.el-collapse-item__content){padding-top:14px}
@media(max-width:700px){.api-request{grid-template-columns:minmax(0,1fr)}.api-request>.api-half{grid-column:1/-1}}
@media(max-width:540px){.request-summary,.editor-error{margin-left:0}.configured{margin-left:6px}}
</style>
