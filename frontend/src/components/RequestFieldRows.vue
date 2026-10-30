<script setup lang="ts">
import type { RequestField } from './requestFields'
defineProps<{ label: string }>()
const rows = defineModel<RequestField[]>({ required: true })
const sensitive = (name: string) => /password|passwd|secret|token|authorization|api[-_]?key/i.test(name)
function remove(index: number) {
  rows.value = rows.value.filter((_, position) => position !== index)
  if (!rows.value.length) rows.value = [{ name: '', value: '' }]
}
</script>

<template>
  <div class="request-fields">
    <div v-for="(row,index) in rows" :key="index" class="request-field-row">
      <el-input v-model="row.name" placeholder="参数名" :aria-label="`${label}第 ${index+1} 行参数名`"/>
      <el-input v-model="row.value" placeholder="参数值" :type="sensitive(row.name)?'password':'text'" :show-password="sensitive(row.name)" :aria-label="`${label}第 ${index+1} 行参数值`"/>
      <el-button text type="danger" :aria-label="`删除${label}第 ${index+1} 行`" @click="remove(index)">×</el-button>
    </div>
    <el-button link type="primary" @click="rows=[...rows,{name:'',value:''}]">＋ 添加参数</el-button>
  </div>
</template>

<style scoped>
.request-fields{width:100%;min-width:0}.request-field-row{display:grid;grid-template-columns:minmax(90px,1fr) minmax(110px,1.5fr) 30px;gap:8px;margin-bottom:8px}.request-field-row .el-button{padding:0;font-size:20px}.request-fields>.el-button{margin-top:2px}
@media(max-width:540px){.request-field-row{grid-template-columns:minmax(0,1fr) minmax(0,1.3fr) 26px;gap:4px}}
</style>
