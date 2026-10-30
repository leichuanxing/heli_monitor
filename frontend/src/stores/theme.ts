import { ref, watch } from 'vue'

export type Theme = 'light' | 'dark'
const key = 'heli_theme'

function initialTheme(): Theme {
  try {
    const saved = localStorage.getItem(key)
    if (saved === 'light' || saved === 'dark') return saved
  } catch { /* Storage can be unavailable in private browsing. */ }
  return typeof matchMedia === 'function' && matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

export const theme = ref<Theme>(initialTheme())

export function applyTheme(value: Theme) {
  document.documentElement.dataset.theme = value
  document.documentElement.classList.toggle('dark', value === 'dark')
  document.documentElement.style.colorScheme = value
}

export function initializeTheme() {
  applyTheme(theme.value)
}

export function toggleTheme() {
  theme.value = theme.value === 'light' ? 'dark' : 'light'
}

watch(theme, value => {
  applyTheme(value)
  try { localStorage.setItem(key, value) } catch { /* Keep the current tab usable. */ }
})
