import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, shallowMount } from '@vue/test-utils'
import UserManagementView from './UserManagementView.vue'
import RoleManagementView from './RoleManagementView.vue'
import DepartmentManagementView from './DepartmentManagementView.vue'
const {get}=vi.hoisted(()=>({get:vi.fn()}))
vi.mock('../api/client',()=>({default:{get}}))
vi.mock('element-plus',()=>({ElMessage:{error:vi.fn(),success:vi.fn(),warning:vi.fn()},ElMessageBox:{confirm:vi.fn()}}))
const global={stubs:{ElButton:{template:'<button><slot/></button>'},...Object.fromEntries(['ElTable','ElTableColumn','ElDialog','ElInput','ElSelect','ElOption','ElPagination','ElForm','ElFormItem','ElSwitch','ElAlert'].map(name=>[name,true])) ,ElCard:{template:'<div><slot/></div>'}},directives:{loading:()=>undefined}}
let wrapper:ReturnType<typeof shallowMount>|undefined
function mockAccount(superuser:boolean){get.mockImplementation((url:string)=>{
 if(url==='/auth/me/')return Promise.resolve({data:{is_superuser:superuser,permissions:['iam.view']}})
 if(url==='/users/options/')return Promise.resolve({data:{roles:[],departments:[]}})
 if(url.includes('permission-catalog'))return Promise.resolve({data:[]})
 return Promise.resolve({data:{results:[],count:41}})
})}
afterEach(()=>{wrapper?.unmount();get.mockReset()})
describe('organization views enforce read-only interaction',()=>{
 it.each([{component:UserManagementView,label:'新增用户'},{component:RoleManagementView,label:'新增角色'},{component:DepartmentManagementView,label:'新增部门'}])('hides management controls for readers and supports paginated totals: $label',async({component,label})=>{
  mockAccount(false);wrapper=shallowMount(component,{global});await flushPromises()
  expect(wrapper.text()).not.toContain(label)
  expect(wrapper.find('el-pagination-stub').attributes('total')).toBe('41')
  wrapper.unmount();mockAccount(true);wrapper=shallowMount(component,{global});await flushPromises()
  expect(wrapper.text()).toContain(label)
 })
})
