import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { flushPromises, shallowMount } from '@vue/test-utils'
import MonitorWallView from './MonitorWallView.vue'
import { theme } from '../stores/theme'
const { get,setOption }=vi.hoisted(()=>({get:vi.fn(),setOption:vi.fn()}))
vi.mock('echarts/core',()=>({use:vi.fn(),init:()=>({setOption,resize:vi.fn(),dispose:vi.fn()}),graphic:{LinearGradient:class{}}}))
vi.mock('../stores/systemSettings',()=>({loadSystemSettings:vi.fn().mockResolvedValue({}),systemSettings:{monitor_wall_refresh_seconds:10}}))
vi.mock('../api/client',()=>({default:{get}}))
beforeEach(()=>{
 vi.useFakeTimers();vi.setSystemTime(new Date('2026-10-22T12:00:00Z'));localStorage.clear();get.mockReset();setOption.mockClear()
 get.mockImplementation((url:string,options:any)=>{
  if(url.includes('reports/sla'))return Promise.reject({response:{status:403}})
  if(url==='/monitors/history/')return Promise.resolve({data:{checked_after:options.params.checked_after,checked_before:options.params.checked_before,
   series:Array.from({length:120},(_,i)=>({id:i,monitor:'task',at:new Date(new Date(options.params.checked_after).getTime()+i*60000).toISOString(),latency_ms:i+1,success:true}))}})
  return Promise.resolve({data:{snapshot_at:'2026-10-22T12:00:00Z',health_rate:100,states:{UP:1},latest_monitors:[{id:'task',name:'Accessible monitor',business:'Business',type:'HTTP',status:'UP'}],recent_incidents:[],probe_stats_24h:{}}})
 })
})
afterEach(()=>{vi.useRealTimers();localStorage.clear()})
it('keeps monitoring data visible when report access is denied',async()=>{
 const wrapper=shallowMount(MonitorWallView);await flushPromises()
 expect(wrapper.text()).toContain('Accessible monitor')
 expect(wrapper.text()).toContain('SLA 数据不可用或无报表查看权限')
 expect(wrapper.text()).not.toContain('数据连接异常');wrapper.unmount()
})
it('defaults to twelve hours and plots every point instead of the latest eighty',async()=>{
 const wrapper=shallowMount(MonitorWallView);await flushPromises()
 const request=get.mock.calls.find(([url])=>url==='/monitors/history/')![1].params
 expect(new Date(request.checked_before).getTime()-new Date(request.checked_after).getTime()).toBe(12*3600000)
 expect(wrapper.find<HTMLSelectElement>('select[aria-label="响应趋势时间周期"]').element.value).toBe('12')
 expect(wrapper.text()).toContain('120 个原始数据点')
 const chart=setOption.mock.calls.find(([option])=>option.xAxis)?.[0]
 expect(chart.series[0].data).toHaveLength(120);wrapper.unmount()
})
it('reloads the selected period and applies its exact bounds to the time axis',async()=>{
 const wrapper=shallowMount(MonitorWallView);await flushPromises()
 await wrapper.find<HTMLSelectElement>('select[aria-label="响应趋势时间周期"]').setValue('6');await flushPromises()
 const request=get.mock.calls.filter(([url])=>url==='/monitors/history/').at(-1)![1].params
 expect(new Date(request.checked_before).getTime()-new Date(request.checked_after).getTime()).toBe(6*3600000)
 const chart=setOption.mock.calls.filter(([option])=>option.xAxis).at(-1)![0]
 expect(chart.xAxis.min).toBe(new Date(request.checked_after).getTime())
 expect(chart.xAxis.max).toBe(new Date(request.checked_before).getTime());wrapper.unmount()
})
it('repaints the theme without fetching or changing probe points',async()=>{
 const wrapper=shallowMount(MonitorWallView);await flushPromises()
 const calls=get.mock.calls.length
 const before=setOption.mock.calls.filter(([option])=>option.xAxis).at(-1)![0]
 theme.value=theme.value==='dark'?'light':'dark';await flushPromises()
 const after=setOption.mock.calls.filter(([option])=>option.xAxis).at(-1)![0]
 expect(get.mock.calls).toHaveLength(calls)
 expect(after.series[0].data).toEqual(before.series[0].data)
 expect(after.xAxis.min).toBe(before.xAxis.min)
 expect(after.tooltip.textStyle.color).not.toBe(before.tooltip.textStyle.color)
 wrapper.unmount();theme.value='light'
})
