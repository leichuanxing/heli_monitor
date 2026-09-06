<script setup lang="ts">
withDefaults(defineProps<{
  icon: 'edit' | 'delete' | 'toggle' | 'run' | 'check' | 'close' | 'refresh'
  label: string
  tone?: 'primary' | 'success' | 'warning' | 'danger' | 'neutral'
  iconOnly?: boolean
  disabled?: boolean
}>(), { tone: 'neutral', iconOnly: false, disabled: false })
defineEmits<{ click: [event: MouseEvent] }>()
</script>

<template>
  <el-tooltip :content="label" placement="top" :show-after="450">
    <button class="table-action" :class="[`is-${tone}`, { 'is-icon-only': iconOnly }]" type="button" :aria-label="label" :disabled="disabled" @click="$emit('click', $event)">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <template v-if="icon==='edit'"><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L8 18l-4 1 1-4Z"/></template>
        <template v-else-if="icon==='delete'"><path d="M4 7h16M9 7V4h6v3M6.5 7l.8 13h9.4l.8-13M10 11v5M14 11v5"/></template>
        <template v-else-if="icon==='toggle'"><circle cx="12" cy="12" r="9"/><path d="M12 7v5M8.5 8.5a5 5 0 1 0 7 0"/></template>
        <template v-else-if="icon==='run'"><circle cx="12" cy="12" r="9"/><path d="m10 8 6 4-6 4Z"/></template>
        <template v-else-if="icon==='check'"><circle cx="12" cy="12" r="9"/><path d="m8 12 2.5 2.5L16 9"/></template>
        <template v-else-if="icon==='close'"><circle cx="12" cy="12" r="9"/><path d="m9 9 6 6M15 9l-6 6"/></template>
        <template v-else><path d="M20 7v5h-5M4 17v-5h5"/><path d="M6.1 9a7 7 0 0 1 11.7-2L20 12M4 12l2.2 5a7 7 0 0 0 11.7-2"/></template>
      </svg>
      <span v-if="!iconOnly">{{ label }}</span>
    </button>
  </el-tooltip>
</template>

<style scoped>
.table-action{height:30px;display:inline-flex;flex:0 0 auto;align-items:center;justify-content:center;gap:5px;padding:0 9px;color:#506176;background:#fff;border:1px solid #dbe3eb;border-radius:5px;font:500 12px/1 inherit;white-space:nowrap;cursor:pointer;transition:border-color .16s,background .16s,color .16s,box-shadow .16s}.table-action svg{width:14px;height:14px;flex:0 0 14px}.table-action:hover{color:#174b7a;border-color:#9fc1dc;background:#f2f8fc;box-shadow:0 2px 5px rgba(22,69,105,.08)}.table-action:disabled{color:#a8b1bd;border-color:#e5e9ee;background:#f7f8fa;cursor:not-allowed;box-shadow:none}.is-primary{color:#175d91;border-color:#b9d2e5;background:#f5faff}.is-success{color:#25714d;border-color:#bddfcd;background:#f4fbf7}.is-warning{color:#956417;border-color:#ead7af;background:#fffaf0}.is-danger{color:#b33b3b;border-color:#ebcaca;background:#fff8f8}.is-danger:not(:disabled):hover{color:#fff;border-color:#c74747;background:#c74747}.is-icon-only{width:30px;padding:0}
</style>
