<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
const props=withDefaults(defineProps<{title:string;hint?:string;total?:number;pageSize?:number;autoRotate?:boolean}>(),{hint:'',pageSize:6,autoRotate:true})
const page=defineModel<number>('page',{default:0})
const hovered=ref(false),count=computed(()=>Math.max(1,Math.ceil((props.total||0)/props.pageSize)))
let timer:ReturnType<typeof setInterval>|undefined
watch(count,()=>{if(page.value>=count.value)page.value=0})
onMounted(()=>{timer=setInterval(()=>{if(props.autoRotate&&!hovered.value&&count.value>1)page.value=(page.value+1)%count.value},10000)})
onBeforeUnmount(()=>{if(timer)clearInterval(timer)})
</script>
<template><section class="wall-panel" @mouseenter="hovered=true" @mouseleave="hovered=false"><header><h2>{{title}}</h2><small>{{hint}}</small></header><div class="panel-body"><slot/></div><footer v-if="total!==undefined"><span>共 {{total}} 项 · {{page+1}} / {{count}}</span><div><button :disabled="count<=1" :aria-label="title+'上一页'" @click="page=(page+count-1)%count">‹</button><button :disabled="count<=1" :aria-label="title+'下一页'" @click="page=(page+1)%count">›</button></div></footer></section></template>
<style scoped>
.wall-panel{min-width:0;min-height:0;padding:13px 16px;display:flex;flex-direction:column;background:linear-gradient(135deg,#0c2136,#0a1b2d);border:1px solid #244961;border-radius:8px;position:relative;box-sizing:border-box}.wall-panel:before{content:'';position:absolute;left:-1px;top:14px;width:3px;height:18px;background:#43d1ef}header{height:31px;flex:none;display:flex;align-items:flex-start;justify-content:space-between;gap:10px;border-bottom:1px solid #1b3b53;margin-bottom:10px}h2{margin:0;font-size:16px;font-weight:600;color:#e2f2ff;line-height:20px}header small{font-size:10px;color:#799bb5;max-width:65%;text-align:right;line-height:16px}.panel-body{flex:1;min-height:0;min-width:0}footer{height:24px;flex:none;display:flex;align-items:flex-end;justify-content:space-between;color:#7b9fb9;font-size:11px}footer div{display:flex;gap:6px}button{width:23px;height:20px;padding:0;border:1px solid #28506b;border-radius:3px;background:#102c42;color:#bdefff;font-size:16px;line-height:16px;cursor:pointer}button:disabled{opacity:.35;cursor:default}button:focus-visible{outline:2px solid #40d5ed}
</style>
