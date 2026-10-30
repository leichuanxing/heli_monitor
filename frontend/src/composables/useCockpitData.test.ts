import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { mount, flushPromises } from '@vue/test-utils'
import { useCockpitData } from './useCockpitData'
const {get}=vi.hoisted(()=>({get:vi.fn()}))
vi.mock('../api/client',()=>({default:{get}}))
vi.mock('../stores/systemSettings',()=>({loadSystemSettings:vi.fn().mockResolvedValue({}),systemSettings:{monitor_wall_refresh_seconds:10}}))
let state:ReturnType<typeof useCockpitData>,wrapper:ReturnType<typeof mount>
beforeEach(()=>{
 vi.useFakeTimers();vi.setSystemTime(new Date('2026-10-29T00:00:00Z'));get.mockReset()
 get.mockImplementation(async(url:string,options:any)=>{
  if(url.includes('/reports/'))throw new Error('forbidden')
  if(url.includes('/history/'))return{data:{checked_after:options.params.checked_after,checked_before:options.params.checked_before,series:Array.from({length:200},(_,id)=>({id,monitor:'one',at:new Date(Date.now()-200000+id*1000).toISOString(),success:true,latency_ms:id}))}}
  return{data:{snapshot_at:new Date().toISOString(),latest_monitors:[{id:'one',name:'Actual task',status:'UP'}],states:{UP:1}}}
 })
 wrapper=mount(defineComponent({setup(){state=useCockpitData();return()=>h('div')}}))
})
afterEach(()=>{wrapper.unmount();vi.useRealTimers()})
it('loads 12 hours of all raw points and tolerates missing report permission',async()=>{
 await flushPromises()
 const request=get.mock.calls.find(([url])=>url==='/monitors/history/')![1].params
 expect(new Date(request.checked_before).getTime()-new Date(request.checked_after).getTime()).toBe(12*3600000)
 expect(state.history.value!.series).toHaveLength(200)
 expect(state.monitors.value[0].name).toBe('Actual task')
 expect(state.slaUnavailable.value).toBe(true)
 expect(state.error.value).toBe('')
 expect(state.slowest.value[0].latency_ms).toBe(199)
})
it('keeps last successful data and exposes failures instead of fabricating a healthy state',async()=>{
 await flushPromises()
 get.mockRejectedValue(new Error('offline'))
 await state.load(true)
 expect(state.monitors.value[0].name).toBe('Actual task')
 expect(state.error.value).toContain('同步异常')
})
it('changes the exact requested period and stops refresh after unmount',async()=>{
 await flushPromises()
 state.periodHours.value=6
 await flushPromises()
 const request=get.mock.calls.filter(([url])=>url==='/monitors/history/').at(-1)![1].params
 expect(new Date(request.checked_before).getTime()-new Date(request.checked_after).getTime()).toBe(6*3600000)
 wrapper.unmount()
 const calls=get.mock.calls.length
 await vi.advanceTimersByTimeAsync(20000)
 expect(get.mock.calls.length).toBe(calls)
})
