import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, shallowMount } from '@vue/test-utils'
import PublicStatusView from './PublicStatusView.vue'
const { get } = vi.hoisted(()=>({get:vi.fn()}))
vi.mock('axios',()=>({default:{get}}))
vi.mock('vue-router',()=>({useRoute:()=>({params:{slug:'services'},query:{token:'test-only-token'}})}))
const data={name:'Services',theme_color:'#123456',overall_status:'PENDING',summary:{total:1,affected:0},updated_at:'2026-10-22T01:00:00Z',monitors:[{id:'1',name:'Waiting probe',business:'Business',type:'PING',status:'PENDING',latency_ms:null}]}
let wrapper:ReturnType<typeof shallowMount>
const global={stubs:{ElSkeleton:true,ElResult:true,ElEmpty:true,ElTag:true,ElInput:true,ElButton:true}}
beforeEach(()=>{vi.useFakeTimers();get.mockReset();get.mockResolvedValue({data})})
afterEach(()=>{wrapper?.unmount();vi.useRealTimers()})
describe('public status reliability',()=>{
 it('sends only the status token and applies the page theme without normalizing pending to healthy',async()=>{
  wrapper=shallowMount(PublicStatusView,{global});await flushPromises()
  expect(get).toHaveBeenCalledWith('/api/v1/public/status/services/',{headers:{'X-Status-Token':'test-only-token'},timeout:20000})
  expect(wrapper.attributes('style')).toContain('--status-theme: #123456')
  expect(wrapper.text()).toContain('等待服务探测数据')
  expect(wrapper.text()).not.toContain('当前运行中服务正常')
 })
 it('clears a previous error after a successful manual refresh',async()=>{
  get.mockRejectedValueOnce({response:{status:503,data:{detail:'Temporary failure'}}})
  wrapper=shallowMount(PublicStatusView,{global});await flushPromises()
  expect(wrapper.find('el-result-stub').exists()).toBe(true)
  await wrapper.get('header button').trigger('click');await flushPromises()
  expect(wrapper.find('el-result-stub').exists()).toBe(false)
  expect(wrapper.text()).toContain('Waiting probe')
 })
 it('refreshes automatically and stops its timer when leaving the page',async()=>{
  wrapper=shallowMount(PublicStatusView,{global});await flushPromises()
  await vi.advanceTimersByTimeAsync(30000);await flushPromises()
  expect(get).toHaveBeenCalledTimes(2)
  wrapper.unmount();await vi.advanceTimersByTimeAsync(60000)
  expect(get).toHaveBeenCalledTimes(2)
 })
})
it('keeps the last snapshot on a temporary failure and marks it stale',async()=>{
 wrapper=shallowMount(PublicStatusView,{global});await flushPromises()
 get.mockRejectedValueOnce({response:{status:503,data:{detail:'Temporary outage'}}})
 await wrapper.get('.refresh-button').trigger('click');await flushPromises()
 expect(wrapper.text()).toContain('Waiting probe')
 expect(wrapper.get('.stale-banner').text()).toContain('上次成功获取的快照')
 expect(wrapper.find('el-result-stub').exists()).toBe(false)
})
it('clears protected data when access is revoked',async()=>{
 wrapper=shallowMount(PublicStatusView,{global});await flushPromises()
 get.mockRejectedValueOnce({response:{status:403,data:{detail:'Token expired'}}})
 await wrapper.get('.refresh-button').trigger('click');await flushPromises()
 expect(wrapper.text()).not.toContain('Waiting probe')
 expect(wrapper.find('el-result-stub').exists()).toBe(true)
 await vi.advanceTimersByTimeAsync(60000)
 expect(get).toHaveBeenCalledTimes(2)
})
it('filters real services by business keyword and state and can clear the filters',async()=>{
 get.mockResolvedValue({data:{...data,summary:{total:2,affected:1},monitors:[...data.monitors,{id:'2',name:'Checkout',business:'Shop',type:'HTTP',status:'DOWN',latency_ms:null}]}})
 wrapper=shallowMount(PublicStatusView,{global});await flushPromises()
 expect(wrapper.findAll('.list article')).toHaveLength(2)
 await wrapper.get('input[aria-label="搜索服务"]').setValue('shop')
 expect(wrapper.findAll('.list article')).toHaveLength(1)
 expect(wrapper.text()).toContain('Checkout')
 await wrapper.get('select').setValue('UP')
 expect(wrapper.find('.no-results').exists()).toBe(true)
 await wrapper.get('.no-results button').trigger('click')
 expect(wrapper.findAll('.list article')).toHaveLength(2)
})
it('pauses and resumes automatic refresh without changing the displayed services',async()=>{
 wrapper=shallowMount(PublicStatusView,{global});await flushPromises()
 await wrapper.get('.auto-toggle').trigger('click')
 await vi.advanceTimersByTimeAsync(30000)
 expect(get).toHaveBeenCalledTimes(1)
 expect(wrapper.text()).toContain('Waiting probe')
 await wrapper.get('.auto-toggle').trigger('click')
 await vi.advanceTimersByTimeAsync(30000);await flushPromises()
 expect(get).toHaveBeenCalledTimes(2)
})
