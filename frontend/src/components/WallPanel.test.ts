import { afterEach, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import WallPanel from './WallPanel.vue'

afterEach(()=>vi.useRealTimers())
it('cycles every page and supports manual navigation and pause',async()=>{
 vi.useFakeTimers()
 const wrapper=mount(WallPanel,{props:{title:'Tasks',total:14,pageSize:6}})
 expect(wrapper.text()).toContain('1 / 3')
 await vi.advanceTimersByTimeAsync(10000)
 expect(wrapper.text()).toContain('2 / 3')
 await wrapper.get('button[aria-label="Tasks下一页"]').trigger('click')
 expect(wrapper.text()).toContain('3 / 3')
 await wrapper.setProps({autoRotate:false})
 await vi.advanceTimersByTimeAsync(20000)
 expect(wrapper.text()).toContain('3 / 3')
 await wrapper.setProps({total:1})
 expect(wrapper.text()).toContain('1 / 1')
 wrapper.unmount()
})
