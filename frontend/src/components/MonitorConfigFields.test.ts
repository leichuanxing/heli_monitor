import { mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { nextTick } from 'vue'
import { describe, expect, it } from 'vitest'
import MonitorConfigFields from './MonitorConfigFields.vue'

describe('MonitorConfigFields', () => {
  it('兼容单个状态码并在同类型任务切换时刷新参数', async () => {
    const wrapper = mount(MonitorConfigFields, {
      props: { type: 'HTTP', modelValue: { expected_status: 200 } },
      global: { plugins: [ElementPlus] },
    })
    expect((wrapper.vm as any).normalize().expected_status).toEqual([200])

    await wrapper.setProps({ modelValue: { expected_status: [204] } })
    await nextTick()
    expect((wrapper.vm as any).normalize().expected_status).toEqual([204])
  })
})
