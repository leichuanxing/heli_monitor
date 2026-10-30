import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
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
 const wrapper=mount(MonitorWallView,{global:{stubs:{RouterLink:{template:'<a><slot/></a>'}}}});await flushPromises()
 expect(wrapper.text()).toContain('Accessible monitor')
 expect(wrapper.text()).toContain('SLA 数据不可用或无报表查看权限')
 expect(wrapper.text()).not.toContain('数据连接异常');wrapper.unmount()
})
it('defaults to twelve hours and plots every point instead of the latest eighty',async()=>{
 const wrapper=mount(MonitorWallView,{global:{stubs:{RouterLink:{template:'<a><slot/></a>'}}}});await flushPromises()
 const request=get.mock.calls.find(([url])=>url==='/monitors/history/')![1].params
 expect(new Date(request.checked_before).getTime()-new Date(request.checked_after).getTime()).toBe(12*3600000)
 expect(wrapper.find<HTMLSelectElement>('select[aria-label="响应趋势时间周期"]').element.value).toBe('12')
 expect(wrapper.text()).toContain('120 个原始点')
 const chart=setOption.mock.calls.find(([option])=>option.xAxis)?.[0]
 expect(chart.series[0].data).toHaveLength(120);wrapper.unmount()
})
it('reloads the selected period and applies its exact bounds to the time axis',async()=>{
 const wrapper=mount(MonitorWallView,{global:{stubs:{RouterLink:{template:'<a><slot/></a>'}}}});await flushPromises()
 await wrapper.find<HTMLSelectElement>('select[aria-label="响应趋势时间周期"]').setValue('6');await flushPromises()
 const request=get.mock.calls.filter(([url])=>url==='/monitors/history/').at(-1)![1].params
 expect(new Date(request.checked_before).getTime()-new Date(request.checked_after).getTime()).toBe(6*3600000)
 const chart=setOption.mock.calls.filter(([option])=>option.xAxis).at(-1)![0]
 expect(chart.xAxis.min).toBe(new Date(request.checked_after).getTime())
 expect(chart.xAxis.max).toBe(new Date(request.checked_before).getTime());wrapper.unmount()
})
it('keeps the wall dark when the management theme changes',async()=>{
 const wrapper=mount(MonitorWallView,{global:{stubs:{RouterLink:{template:'<a><slot/></a>'}}}});await flushPromises()
 expect(setOption.mock.calls.filter(([option])=>option.xAxis).at(-1)![0].tooltip.backgroundColor).toBe('#1c2a3d')
 const calls=get.mock.calls.length
 const before=setOption.mock.calls.filter(([option])=>option.xAxis).at(-1)![0]
 theme.value=theme.value==='dark'?'light':'dark';await flushPromises()
 const after=setOption.mock.calls.filter(([option])=>option.xAxis).at(-1)![0]
 expect(get.mock.calls).toHaveLength(calls)
 expect(after.series[0].data).toEqual(before.series[0].data)
 expect(after.xAxis.min).toBe(before.xAxis.min)
 expect(after.tooltip.textStyle.color).toBe('#e8eef7')
 expect(after.tooltip.backgroundColor).toBe(before.tooltip.backgroundColor)
 expect(wrapper.attributes('data-wall-theme')).toBe('dark')
 wrapper.unmount();theme.value='light'
})

it('makes every SLA and monitor reachable through explicit single-screen pagination',async()=>{
 const previous=get.getMockImplementation()!
 get.mockImplementation(async(url:string,options:any)=>{
  if(url==='/reports/sla/')return{data:{results:Array.from({length:12},(_,i)=>({monitor_id:`m${i}`,monitor_name:`SLA monitor ${i}`,availability:100,samples:10}))}}
  const response=await previous(url,options)
  if(url==='/dashboard/summary/')response.data.latest_monitors=Array.from({length:14},(_,i)=>({id:`m${i}`,name:`Node ${i}`,business:'Business',type:'HTTP',status:'UP'}))
  return response
 })
 const wrapper=mount(MonitorWallView,{global:{stubs:{RouterLink:{template:'<a><slot/></a>'}}}});await flushPromises()
 await wrapper.find('.header-actions button').trigger('click')
 const names=new Set<string>(),nodes=new Set<string>()
 for(let page=0;page<3;page++){
  expect(wrapper.findAll('.sla-row')).toHaveLength(4)
  wrapper.findAll('.sla-row>b').forEach(row=>names.add(row.text()))
  wrapper.findAll('.nodes article>b').forEach(row=>nodes.add(row.text()))
  await wrapper.find('button[aria-label="24H SLA 可用率下一页"]').trigger('click')
  await wrapper.find('button[aria-label="业务健康节点下一页"]').trigger('click')
 }
 expect(names.size).toBe(12);expect(names.has('SLA monitor 11')).toBe(true)
 expect(nodes.size).toBe(14);expect(nodes.has('Node 13')).toBe(true)
 const chart=setOption.mock.calls.find(([option])=>option.xAxis)?.[0]
 expect(chart.legend.type).toBe('scroll')
 wrapper.unmount()
})

it('summarizes real business states and selected-period peaks in the cockpit',async()=>{
 const wrapper=mount(MonitorWallView,{global:{stubs:{RouterLink:{template:'<a><slot/></a>'}}}});await flushPromises()
 expect(wrapper.find('.brief').text()).toContain('业务运行平稳')
 expect(wrapper.find('.business-row').text()).toContain('Business')
 expect(wrapper.find('.business-row').text()).toContain('1 / 1 正常')
 expect(wrapper.find('.window-summary').text()).toContain('120.0')
 expect(wrapper.find('.window-summary').text()).toContain('100.0')
 wrapper.unmount()
})

it('prioritizes real faults and does not invent zero latency for missing responses',async()=>{
 const previous=get.getMockImplementation()!
 get.mockImplementation(async(url:string,options:any)=>{
  const response=await previous(url,options)
  if(url==='/dashboard/summary/'){response.data.states={DOWN:1};response.data.latest_monitors[0].status='DOWN'}
  if(url==='/monitors/history/')response.data.series=response.data.series.map((point:any)=>({...point,latency_ms:null,success:false}))
  return response
 })
 const wrapper=mount(MonitorWallView,{global:{stubs:{RouterLink:{template:'<a><slot/></a>'}}}});await flushPromises()
 expect(wrapper.find('.posture').classes()).toContain('risk')
 expect(wrapper.find('.posture h2').text()).toBe('发现异常，需要关注')
 expect(wrapper.findAll('.window-summary b')[2].text()).toContain('—')
 expect(wrapper.find('.business-row').text()).toContain('故障 1')
 wrapper.unmount()
})

it('lets operators pause decorative motion without fetching or changing monitoring data',async()=>{
 const wrapper=mount(MonitorWallView,{global:{stubs:{RouterLink:{template:'<a><slot/></a>'}}}});await flushPromises()
 const count=get.mock.calls.length
 const samples=wrapper.find('.window-summary').text()
 expect(wrapper.classes()).not.toContain('motion-paused')
 await wrapper.find('.header-actions button').trigger('click')
 expect(wrapper.classes()).toContain('motion-paused')
 expect(wrapper.find('.header-actions button').attributes('aria-pressed')).toBe('true')
 expect(wrapper.find('.header-actions button').text()).toBe('继续轮播 / 动效')
 expect(get.mock.calls).toHaveLength(count)
 expect(wrapper.find('.window-summary').text()).toBe(samples)
 await wrapper.find('.header-actions button').trigger('click')
 expect(wrapper.classes()).not.toContain('motion-paused')
 wrapper.unmount()
})
