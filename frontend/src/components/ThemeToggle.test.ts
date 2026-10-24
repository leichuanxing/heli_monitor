import { afterEach, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import ThemeToggle from './ThemeToggle.vue'
import { initializeTheme, theme } from '../stores/theme'
import { chartAppearance } from '../composables/chartAppearance'

afterEach(async () => {
  theme.value = 'light'
  await nextTick()
  localStorage.removeItem('heli_theme')
})

it('switches the whole workspace and charts together and remembers the choice', async () => {
  theme.value = 'light'
  initializeTheme()
  const wrapper = mount(ThemeToggle)
  const lightChart = chartAppearance()
  await wrapper.get('button').trigger('click')
  expect(document.documentElement.dataset.theme).toBe('dark')
  expect(document.documentElement.classList.contains('dark')).toBe(true)
  expect(wrapper.get('button').attributes('aria-label')).toBe('切换浅色主题')
  expect(localStorage.getItem('heli_theme')).toBe('dark')
  expect(chartAppearance().tooltip.textStyle.color).not.toBe(lightChart.tooltip.textStyle.color)
  await wrapper.get('button').trigger('click')
  expect(document.documentElement.dataset.theme).toBe('light')
  expect(document.documentElement.classList.contains('dark')).toBe(false)
  wrapper.unmount()
})
