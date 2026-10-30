import { afterEach, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { reactive } from 'vue'
import ElementPlus, { ElMessageBox } from 'element-plus'
import MonitorTaskForm from './MonitorTaskForm.vue'
import MonitorConfigFields from './MonitorConfigFields.vue'

let wrapper: ReturnType<typeof mount>
afterEach(()=>{wrapper?.unmount();vi.restoreAllMocks()})
function create(extra:Record<string,any>={}) {
 const value=reactive<Record<string,any>>({name:'Existing task',business:'business-1',target:'example.com',monitor_type:'HTTP',interval_seconds:60,timeout_seconds:10,failure_threshold:3,recovery_threshold:2,warning_latency_ms:null,is_enabled:true,tags:[],config:{},...extra})
 wrapper=mount(MonitorTaskForm,{props:{modelValue:value,businesses:[{id:'business-1',name:'Business'}],tags:[]},global:{plugins:[ElementPlus]}})
 return value
}
const normalize=()=> (wrapper.vm as unknown as {normalize:()=>Record<string,any>}).normalize()
const typeSelect=()=>wrapper.findAllComponents({name:'ElSelect'}).find(select=>select.props('modelValue')==='HTTP')!

it('keeps current scheduling, masked credentials and tags on edit',()=>{
 const value=create({id:'task-1',interval_seconds:37,timeout_seconds:9,tags:['tag-1'],config:{method:'POST',auth:{type:'basic',username:'user',password:'********'},json:{id:42,enabled:false}}})
 const result=normalize()
 expect(value.interval_seconds).toBe(37)
 expect(value.timeout_seconds).toBe(9)
 expect(value.tags).toEqual(['tag-1'])
 expect(result.auth.password).toBe('********')
 expect(result.json).toEqual({id:42,enabled:false})
})
it('uses protocol recommendations for a new task without overwriting custom values',async()=>{
 const value=create()
 typeSelect().vm.$emit('update:modelValue','PING')
 await flushPromises()
 expect([value.interval_seconds,value.timeout_seconds]).toEqual([30,5])
 const ping=wrapper.findAllComponents({name:'ElSelect'}).find(select=>select.props('modelValue')==='PING')!
 value.interval_seconds=47;value.timeout_seconds=7
 ping.vm.$emit('update:modelValue','SSL')
 await flushPromises()
 expect([value.interval_seconds,value.timeout_seconds]).toEqual([47,7])
})
it('does not clear existing protocol configuration when type change is cancelled',async()=>{
 const value=create({id:'task-1',config:{method:'POST',json:{keep:true}}})
 vi.spyOn(ElMessageBox,'confirm').mockRejectedValue('cancel')
 typeSelect().vm.$emit('update:modelValue','DNS')
 await flushPromises()
 expect(value.monitor_type).toBe('HTTP')
 expect(value.config.json).toEqual({keep:true})
})
it('rejects invalid common schedule before sending requests',()=>{
 const value=create()
 value.interval_seconds=10;value.timeout_seconds=10
 expect(normalize).toThrow('超时时间必须小于探测周期')
})

it.each([
 ['TCP',{send:'PING\\r\\n',expect:'PONG',receive_bytes:8192,send_escapes:false}],
 ['PING',{count:5,max_packet_loss:33.33}],
 ['DNS',{record_type:'AAAA',server:'2001:db8::1',expected:['2001:db8::2']}],
 ['SSL',{warn_days:14,expiry_action:'warn'}],
 ['MSSQL',{database:'business',username:'u',password:'********',query:'SELECT 1',tds_version:'7.3'}],
 ['POSTGRESQL',{database:'business',username:'u',password:'********',query:'SELECT 1',sslmode:'verify-full'}],
 ['MYSQL',{database:'business',username:'u',password:'********',query:'SELECT 1',use_tls:true}],
 ['MONGODB',{database:'business',auth_enabled:false,use_tls:true}],
])('preserves the saved %s protocol parameters', (type, config)=>{
 create({id:'task-1',monitor_type:type,config:structuredClone(config)})
 expect(normalize()).toMatchObject(config)
})
it('does not add a database result assertion or change a missing SSL notification policy',()=>{
 create({id:'task-1',monitor_type:'MYSQL',config:{database:'app',username:'u',password:'********',query:'SELECT 1'}})
 expect(normalize().expected_value).toBeUndefined()
 wrapper.unmount()
 create({id:'task-2',monitor_type:'SSL',config:{warn_days:7}})
 expect(normalize().expiry_action).toBeUndefined()
})
it('exposes TCP read limits without dropping protocol parameters',()=>{
 create({id:'task-1',monitor_type:'TCP',config:{send:'',expect:'',receive_bytes:4096}})
 expect(wrapper.findComponent(MonitorConfigFields).text()).toContain('最大读取字节')
 expect(normalize().receive_bytes).toBe(4096)
})
