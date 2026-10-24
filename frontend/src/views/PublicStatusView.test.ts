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
