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
.table-action{height:30px;display:inline-flex;flex:0 0 auto;align-items:center;justify-content:center;gap:5px;padding:0 9px;color:var(--text-secondary);background:transparent;border:1px solid var(--border);border-radius:6px;font:500 12px/1 inherit;white-space:nowrap;cursor:pointer}.table-action svg{width:14px;height:14px;flex:none}.table-action:hover{color:var(--brand);border-color:var(--brand);background:var(--brand-soft)}.table-action:disabled{opacity:.5;color:var(--muted);border-color:var(--border);background:var(--surface-subtle);cursor:not-allowed;box-shadow:none}.is-primary{color:var(--brand);background:var(--brand-soft);border-color:transparent}.is-success{color:var(--success);background:var(--success-soft);border-color:transparent}.is-warning{color:var(--warning);background:var(--warning-soft);border-color:transparent}.is-danger{color:var(--danger);border-color:transparent}.is-danger:not(:disabled):hover{color:var(--danger);border-color:var(--danger);background:var(--danger-soft)}.is-icon-only{width:30px;padding:0}
</style>
