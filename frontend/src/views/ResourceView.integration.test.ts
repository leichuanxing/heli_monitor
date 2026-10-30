import { afterEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import ResourceView from './ResourceView.vue'
import MonitorConfigFields from '../components/MonitorConfigFields.vue'
import { resourceConfigs } from '../config/resources'
const { get, post } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('../api/client', () => ({ default: { get, post } }))
vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }) }))
let wrapper: ReturnType<typeof mount>
afterEach(() => { wrapper?.unmount(); document.body.innerHTML = '' })
it('keeps only one object editor for probe configuration and preserves TLS defaults', async () => {
 get.mockImplementation(async (url:string) => ({ data: url.includes('auth/me') ? { is_superuser:true, permissions:[] } : url.includes('options') ? { businesses:[],tags:[] } : { results:[],count:0 } }))
 wrapper=mount(ResourceView,{props:{config:resourceConfigs.monitors},attachTo:document.body,global:{plugins:[ElementPlus]}})
 await flushPromises()
 const add=wrapper.findAll('button').find(b=>b.text()==='新增')
 expect(add).toBeDefined(); await add!.trigger('click'); await flushPromises()
 const fields=wrapper.findComponent(MonitorConfigFields)
 expect(fields.exists()).toBe(true)
 expect(typeof fields.props('modelValue')).toBe('object')
 expect((fields.vm as unknown as {normalize:()=>Record<string,unknown>}).normalize().verify_tls).toBe(true)
 const genericJson=wrapper.findAll('.el-form-item').filter(item=>item.text().startsWith('高级配置'))
 expect(genericJson).toHaveLength(0)
})

it('shows essential API scheduling and folds alert policy without changing defaults', async () => {
 get.mockImplementation(async (url:string) => ({ data: url.includes('auth/me') ? { is_superuser:true, permissions:[] } : url.includes('options') ? { businesses:[],tags:[] } : { results:[],count:0 } }))
 wrapper=mount(ResourceView,{props:{config:resourceConfigs.monitors},attachTo:document.body,global:{plugins:[ElementPlus]}})
 await flushPromises()
 await wrapper.findAll('button').find(button=>button.text()==='新增')!.trigger('click')
 await flushPromises()
 const type=wrapper.findAllComponents({name:'ElSelect'}).find(select=>select.props('modelValue')==='HTTP')!
 type.vm.$emit('update:modelValue','API')
 await flushPromises()
 expect(wrapper.findAll('.el-form-item').some(item=>item.text().startsWith('周期（秒）'))).toBe(true)
 expect(wrapper.get('.task-advanced .el-collapse-item__header').attributes('aria-expanded')).toBe('false')
 expect(wrapper.text()).toContain('每 60 秒检查 · 超时 10 秒')
 expect(wrapper.text()).toContain('接口地址')
 const fields=wrapper.findComponent(MonitorConfigFields)
 expect((fields.vm as unknown as {normalize:()=>Record<string,unknown>}).normalize().verify_tls).toBe(true)
 await wrapper.get('.task-advanced .el-collapse-item__header').trigger('click')
 await flushPromises()
 expect(wrapper.get('.task-advanced .el-collapse-item__header').attributes('aria-expanded')).toBe('true')
 expect(wrapper.text()).toContain('每 60 秒检查 · 超时 10 秒')
})
