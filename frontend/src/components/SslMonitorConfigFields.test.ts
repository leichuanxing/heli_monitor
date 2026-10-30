import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import MonitorConfigFields from './MonitorConfigFields.vue'

describe('SSL expiry settings', () => {
  it('offers notification reminders and defaults new certificates to 30 days', () => {
    const model: Record<string, unknown> = {}
    const wrapper = mount(MonitorConfigFields, { props: { type: 'SSL', modelValue: model }, global: { plugins: [ElementPlus] } })
    expect(model.warn_days).toBe(30)
    expect(model.expiry_action).toBe('notify')
    expect(wrapper.text()).toContain('提前提醒天数')
    expect(wrapper.text()).toContain('告警规则及通知渠道')
    wrapper.unmount()
  })
  it('preserves existing page-only and failure policies', () => {
    for (const action of ['warn', 'fail']) {
      const model = { warn_days: 7, expiry_action: action }
      const wrapper = mount(MonitorConfigFields, { props: { type: 'SSL', modelValue: model }, global: { plugins: [ElementPlus] } })
      expect(model).toEqual({ warn_days: 7, expiry_action: action })
      wrapper.unmount()
    }
  })
})
