<script setup lang="ts">
import { theme, toggleTheme } from '../stores/theme'
</script>

<template>
  <button class="theme-toggle" type="button" :aria-label="theme === 'light' ? '切换深色主题' : '切换浅色主题'" :title="theme === 'light' ? '切换深色主题' : '切换浅色主题'" :aria-pressed="theme === 'dark'" @click="toggleTheme">
    <svg v-if="theme === 'light'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20.5 14A8.5 8.5 0 0 1 10 3.5 8.5 8.5 0 1 0 20.5 14Z"/></svg>
    <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.5 1.5m11 11L19 19M5 19l1.5-1.5m11-11L19 5"/></svg>
  </button>
</template>

<style scoped>
.theme-toggle{display:inline-grid;place-items:center;flex:0 0 34px;width:34px;height:34px;border:1px solid var(--border);border-radius:8px;background:var(--surface);color:var(--text-secondary);cursor:pointer}.theme-toggle:hover{background:var(--brand-soft);border-color:var(--brand);color:var(--brand)}svg{width:18px;height:18px}
</style>
