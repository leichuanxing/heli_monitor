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

describe('探测参数完整性',()=>{
  const mountConfig=(type:string,config:Record<string,any>)=>mount(MonitorConfigFields,{props:{type,modelValue:config},global:{plugins:[ElementPlus]}})
  it('编辑表单请求体时保留表单类型',()=>{
    const wrapper=mountConfig('API',{method:'POST',form:{name:'测试'},auth:{type:'none'}})
    const value=(wrapper.vm as any).normalize()
    expect(value.form).toEqual({name:'测试'})
    expect(value.json).toBeUndefined()
  })
  it('编辑原始文本请求体时不改写内容',()=>{
    const wrapper=mountConfig('HTTP',{method:'POST',body:'ping\r\n正文'})
    expect((wrapper.vm as any).normalize().body).toBe('ping\r\n正文')
    expect(wrapper.text()).toContain('请求体类型')
    expect(wrapper.text()).toContain('认证方式')
  })
  it('期望状态码留空时使用全部2xx',()=>{
    const wrapper=mountConfig('HTTP',{method:'GET'})
    expect((wrapper.vm as any).normalize().expected_status).toBeUndefined()
  })
  it('非法状态码不会被静默忽略',async()=>{
    const wrapper=mountConfig('HTTP',{expected_status:[200]})
    const field=wrapper.findAll('.el-form-item').find(item=>item.text().includes('期望状态码'))!
    await field.find('input').setValue('200, abc')
    expect(()=>(wrapper.vm as any).normalize()).toThrow('期望状态码')
  })
  it('数据库期望结果留空时取消结果断言',()=>{
    const wrapper=mountConfig('MYSQL',{database:'app',username:'u',password:'********',expected_value:''})
    expect((wrapper.vm as any).normalize().expected_value).toBeUndefined()
  })
  it('JSON断言会保留路径和值',()=>{
    const wrapper=mountConfig('API',{json_assertions:[{path:'$.status',value:'ok'}]})
    expect((wrapper.vm as any).normalize().json_assertions).toEqual([{path:'$.status',value:'ok'}])
  })
})
