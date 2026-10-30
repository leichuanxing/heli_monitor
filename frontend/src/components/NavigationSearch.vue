<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { searchNavigation, type NavigationItem } from './navigationSearch'
const props = defineProps<{ modelValue: boolean; items: NavigationItem[] }>()
const emit = defineEmits<{ 'update:modelValue': [value: boolean]; navigate: [path: string] }>()
const query = ref(''), selected = ref(0), input = ref<{ focus: () => void }>(), resultList = ref<HTMLElement>()
const results = computed(() => searchNavigation(props.items, query.value))
watch(query, () => { selected.value = 0 })
watch(selected, async () => { await nextTick(); resultList.value?.children.item(selected.value)?.scrollIntoView({block: 'nearest'}) })
watch(() => props.modelValue, async value => { if (value) { query.value = ''; selected.value = 0; await nextTick(); input.value?.focus() } })
function choose(path: string) { emit('update:modelValue', false); emit('navigate', path) }
function move(delta: number) { if (results.value.length) selected.value = (selected.value + delta + results.value.length) % results.value.length }
function enter() { const item = results.value[selected.value]; if (item) choose(item.path) }
</script>
<template>
  <el-dialog :model-value="modelValue" title="快速前往" width="560px" class="navigation-search" @opened="input?.focus()" @update:model-value="emit('update:modelValue', $event)">
    <el-input ref="input" v-model="query" placeholder="搜索页面名称、模块或路径" clearable aria-label="搜索页面" @keydown.down.prevent="move(1)" @keydown.up.prevent="move(-1)" @keydown.enter.prevent="enter" />
    <div ref="resultList" class="navigation-results" aria-label="可访问页面">
      <button v-for="(item,index) in results" :key="item.path" type="button" :class="{selected:index===selected}" :aria-current="index===selected ? 'true' : undefined" @click="choose(item.path)"><span>{{item.title}}<small>{{item.group}}</small></span><span aria-hidden="true">↗</span></button>
      <el-empty v-if="!results.length" description="没有匹配页面，请尝试其他关键词" :image-size="64" />
    </div>
    <template #footer><span class="search-hint">↑ ↓ 选择 · Enter 前往 · Esc 关闭</span></template>
  </el-dialog>
</template>
<style scoped>
.navigation-results{margin-top:14px;max-height: min(420px,50vh);overflow:auto;display:grid;gap:4px}.navigation-results button{display:flex;align-items:center;justify-content:space-between;text-align:left;padding:12px 14px;border:1px solid transparent;border-radius:8px;background:var(--surface);color:var(--text-primary);font:inherit;cursor:pointer}.navigation-results button:hover,.navigation-results button.selected{background:#edf5fc;border-color:#c9def0}.navigation-results small{display:block;font-size:12px;color:var(--muted);margin-top:4px}.search-hint{font-size:12px;color:var(--muted)}
</style>
