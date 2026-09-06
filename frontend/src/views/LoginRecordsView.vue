<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import client from '../api/client'

const rows=ref<any[]>([]),loading=ref(false),search=ref(''),success=ref(''),dates=ref<any[]>([])
const fmt=(value:string)=>value?new Date(value).toLocaleString():'—'
async function load(){loading.value=true;try{const params:any={search:search.value||undefined,success:success.value||undefined,ordering:'-created_at',page_size:100};if(dates.value?.length){params.created_after=dates.value[0];params.created_before=dates.value[1]}const{data}=await client.get('/login-records/',{params});rows.value=data.results||data}catch(e:any){ElMessage.error(e.response?.data?.message||'登录记录加载失败')}finally{loading.value=false}}
function reset(){search.value='';success.value='';dates.value=[];load()}
onMounted(load)
</script>

<template><div class="heading"><div><h2>登录记录</h2><p>查看用户登录结果、来源地址和客户端信息</p></div><div class="toolbar"><el-input v-model="search" clearable placeholder="用户名 / IP / 客户端" @keyup.enter="load"/><el-select v-model="success" clearable placeholder="全部结果"><el-option label="成功" value="true"/><el-option label="失败" value="false"/></el-select><el-date-picker v-model="dates" type="datetimerange" value-format="YYYY-MM-DDTHH:mm:ssZ" start-placeholder="开始时间" end-placeholder="结束时间"/><el-button @click="reset">重置</el-button><el-button type="primary" @click="load">查询</el-button></div></div><el-card shadow="never"><el-table v-loading="loading" :data="rows" stripe><el-table-column label="用户" min-width="150"><template #default="s"><b>{{s.row.user_display||s.row.username}}</b><small>@{{s.row.username}}</small></template></el-table-column><el-table-column label="结果" width="90"><template #default="s"><el-tag :type="s.row.success?'success':'danger'">{{s.row.success?'成功':'失败'}}</el-tag></template></el-table-column><el-table-column prop="source_ip" label="来源 IP" min-width="150"><template #default="s">{{s.row.source_ip||'未知'}}</template></el-table-column><el-table-column prop="user_agent" label="客户端" min-width="360" show-overflow-tooltip/><el-table-column label="失败原因" min-width="150"><template #default="s">{{s.row.success?'—':s.row.failure_reason||'认证失败'}}</template></el-table-column><el-table-column label="登录时间" width="180"><template #default="s">{{fmt(s.row.created_at)}}</template></el-table-column></el-table></el-card></template>

<style scoped>.heading{display:flex;justify-content:space-between;align-items:flex-end;margin-bottom:16px}.heading h2{margin:0;color:#192c42}.heading p{margin:5px 0 0;color:#7f8e9f}.toolbar{display:flex;gap:7px}.toolbar .el-input{width:190px}.toolbar .el-select{width:115px}.toolbar .el-date-editor{width:330px}small{display:block;color:#8794a3;margin-top:4px}</style>
