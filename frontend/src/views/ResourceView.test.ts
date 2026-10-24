import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, shallowMount } from '@vue/test-utils'
import ResourceView from './ResourceView.vue'
import type { ResourceConfig } from '../config/resources'
const { get } = vi.hoisted(()=>({get:vi.fn()}))
vi.mock('../api/client',()=>({default:{get}}))
vi.mock('vue-router',()=>({useRouter:()=>({push:vi.fn()})}))
vi.mock('element-plus',()=>({ElMessage:{error:vi.fn(),success:vi.fn()},ElMessageBox:{confirm:vi.fn()}}))
const global={stubs:Object.fromEntries(['ElTable','ElTableColumn','ElDialog','ElInput','ElButton','ElSelect','ElOption','ElCard','ElPagination','ElForm','ElFormItem','ElInputNumber','ElSwitch','ElProgress','ElAlert','ElTag'].map(name=>[name,true])),directives:{loading:()=>undefined}}
const config={endpoint:'monitors',title:'Tasks',fields:[],columns:[]} as ResourceConfig
let wrapper:ReturnType<typeof shallowMount>
let progress:()=>Promise<unknown>
beforeEach(()=>{
 vi.useFakeTimers();sessionStorage.clear();sessionStorage.setItem('monitor_batch_token','signed-token')
 get.mockReset();progress=()=>Promise.reject(new Error('network unavailable'))
 get.mockImplementation((url:string)=>{
  if(url.includes('batch-status'))return progress()
  if(url==='/auth/me/')return Promise.resolve({data:{is_superuser:true,permissions:[]}})
  if(url.includes('options'))return Promise.resolve({data:{businesses:[],tags:[]}})
  return Promise.resolve({data:{results:[],count:0}})
 })
})
afterEach(()=>{wrapper?.unmount();vi.useRealTimers();sessionStorage.clear()})
describe('batch progress recovery',()=>{
 it('keeps progress token through a network failure and retrieves completion',async()=>{
  wrapper=shallowMount(ResourceView,{props:{config},global});await flushPromises()
  expect(sessionStorage.getItem('monitor_batch_token')).toBe('signed-token')
  progress=()=>Promise.resolve({data:{done:true,total:1,completed:1,passed:1,failed:0,skipped:0,results:[]}})
  await vi.advanceTimersByTimeAsync(5000);await flushPromises()
  expect(get.mock.calls.filter(([url])=>url.includes('batch-status'))).toHaveLength(2)
  expect(sessionStorage.getItem('monitor_batch_token')).toBeNull()
 })
 it('ignores a stale failure after leaving and returning to the page',async()=>{
  let rejectOld!:(reason:unknown)=>void
  progress=()=>new Promise((_,reject)=>{rejectOld=reject})
  wrapper=shallowMount(ResourceView,{props:{config},global});await flushPromises()
  await wrapper.setProps({config:{...config,endpoint:'tags'}});await flushPromises()
  progress=()=>Promise.reject(new Error('temporary failure'))
  await wrapper.setProps({config});await flushPromises()
  rejectOld({response:{status:400}});await flushPromises()
  expect(sessionStorage.getItem('monitor_batch_token')).toBe('signed-token')
 })
 it('stops polling invalid or expired tokens',async()=>{
  progress=()=>Promise.reject({response:{status:400,data:{detail:'expired'}}})
  wrapper=shallowMount(ResourceView,{props:{config},global});await flushPromises()
  await vi.advanceTimersByTimeAsync(10000)
  expect(sessionStorage.getItem('monitor_batch_token')).toBeNull()
  expect(get.mock.calls.filter(([url])=>url.includes('batch-status'))).toHaveLength(1)
 })
 it('resumes progress when a reused resource view returns to monitors',async()=>{
  wrapper=shallowMount(ResourceView,{props:{config},global});await flushPromises()
  await wrapper.setProps({config:{...config,endpoint:'tags'}});await flushPromises()
  await vi.advanceTimersByTimeAsync(10000)
  expect(get.mock.calls.filter(([url])=>url.includes('batch-status'))).toHaveLength(1)
  await wrapper.setProps({config});await flushPromises()
  expect(get.mock.calls.filter(([url])=>url.includes('batch-status'))).toHaveLength(2)
 })
})

it('loads asset form options without requesting organization endpoints and hides readonly actions',async()=>{
 get.mockImplementation((url:string)=>{
  if(url==='/auth/me/')return Promise.resolve({data:{is_superuser:false,permissions:['asset.view']}})
  if(url==='/business-systems/options/')return Promise.resolve({data:{'business-groups':[],departments:[],users:[],tags:[]}})
  return Promise.resolve({data:{results:[],count:0}})
 })
 wrapper=shallowMount(ResourceView,{props:{config:{...config,endpoint:'business-systems'}},global:{...global,stubs:{...global.stubs,ElButton:{template:'<button><slot/></button>'}}}})
 await flushPromises()
 expect(get.mock.calls.some(([url])=>url==='/business-systems/options/')).toBe(true)
 expect(get.mock.calls.some(([url])=>url==='/users/'||url==='/departments/')).toBe(false)
 expect(wrapper.text()).not.toContain('新增')
})
