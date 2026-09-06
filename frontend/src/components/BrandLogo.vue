<script setup lang="ts">
withDefaults(defineProps<{ theme?: 'light' | 'dark'; compact?: boolean; text?: string }>(), {
  theme: 'light',
  compact: false,
  text: '合力数据',
})
</script>

<template>
  <div class="brand-logo" :class="[`is-${theme}`, { 'is-compact': compact }]" aria-label="合力数据业务监控平台">
    <span class="brand-words">
      <strong>{{ compact ? text.slice(0, 1) : text }}</strong>
    </span>
  </div>
</template>

<style scoped>
.brand-logo{display:inline-flex;align-items:center;white-space:nowrap}.brand-words{display:flex;flex-direction:column;line-height:1}.brand-words strong{font-size:18px;font-weight:750;letter-spacing:.1em}.brand-words small{font-size:8px;font-weight:650;letter-spacing:.16em;margin-top:7px}.is-light .brand-words strong{color:#22364a}.is-light .brand-words small{color:#7f91a2}.is-dark .brand-words strong{color:#f4f9fc}.is-dark .brand-words small{color:#7293ab}.is-compact .brand-words strong{width:38px;text-align:center;font-size:21px;letter-spacing:0}
.brand-logo{width:100%;justify-content:center;text-align:center}
</style>
