<script setup lang="ts">
import { computed, defineAsyncComponent } from 'vue'
import { useRoute, useRouter } from 'vue-router'
const route=useRoute(),router=useRouter()
const Results=defineAsyncComponent(()=>import('./MonitorResultsView.vue'))
const History=defineAsyncComponent(()=>import('./MonitorHistoryView.vue'))
const active=computed({
 get:()=>route.query.view==='history'?'history':'results',
 set:(view:string)=>{router.replace({path:'/monitor-results',query:{...route.query,view:view==='history'?'history':undefined}})},
})
</script>
<template>
 <el-tabs v-model="active" class="monitor-data-tabs">
  <el-tab-pane label="结果明细" name="results"/>
  <el-tab-pane label="历史趋势" name="history"/>
 </el-tabs>
 <History v-if="active==='history'"/>
 <Results v-else/>
</template>
<style scoped>.monitor-data-tabs{margin-bottom:12px}</style>
