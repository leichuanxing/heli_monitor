<script setup lang="ts">
withDefaults(defineProps<{ theme?: 'light' | 'dark'; compact?: boolean; text?: string }>(), {
  theme: 'light',
  compact: false,
  text: '合力数据',
})
</script>

<template>
  <div class="brand-logo" :class="[`is-${theme}`, { 'is-compact': compact }]" aria-label="合力数据业务监控平台">
    <svg class="brand-mark" viewBox="0 0 36 36" fill="none" aria-hidden="true"><rect width="36" height="36" rx="10" fill="#2867dc"/><path d="M10 10v16m16-16v16M10 18h6l3-6 3 12 4-6" stroke="white" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>
    <span v-if="!compact" class="brand-words">
      <strong>{{ text }}</strong>
      <small>HELI MONITOR</small>
    </span>
  </div>
</template>

<style scoped>
.brand-logo{display:inline-flex;align-items:center;gap:11px;white-space:nowrap;min-width:0}.brand-mark{width:36px;height:36px;flex:none}.brand-words{display:flex;flex-direction:column;line-height:1.15;min-width:0}.brand-words strong{font-size:15px;font-weight:750;letter-spacing:.025em;overflow:hidden;text-overflow:ellipsis;max-width:168px}.brand-words small{font-size:9px;font-weight:600;letter-spacing:.18em;margin-top:5px;color:var(--muted)}.is-light .brand-words strong{color:var(--text-primary)}.is-dark .brand-words strong{color:#edf3ff}.is-dark .brand-words small{color:#93a9c8}.is-compact{justify-content:center;width:100%}
</style>
