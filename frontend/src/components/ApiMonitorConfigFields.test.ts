import { afterEach, describe, expect, it } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import MonitorConfigFields from './MonitorConfigFields.vue'
import ApiMonitorConfigFields from './ApiMonitorConfigFields.vue'
import { fieldRows, fieldsObject, isTextObject } from './requestFields'

let wrapper: ReturnType<typeof mount>
afterEach(() => wrapper?.unmount())
const mountApi = (value: Record<string, unknown>) => {
  wrapper = mount(MonitorConfigFields, { props: { type: 'API', modelValue: value }, global: { plugins: [ElementPlus] } })
  return wrapper
}
const normalize = () => (wrapper.vm as unknown as { normalize: () => Record<string, any> }).normalize()

describe('API simple configuration', () => {
  it('defaults to all 2xx without exposing advanced controls', () => {
    mountApi({})
    expect(wrapper.text()).toContain('默认接受全部 2xx（包含 200、201）')
    expect(wrapper.get('.el-collapse-item__header').attributes('aria-expanded')).toBe('false')
    const value = normalize()
    expect(value.expected_status).toBeUndefined()
    expect(value.verify_tls).toBe(true)
    expect(value.method).toBe('GET')
    expect(value.auth).toEqual({ type: 'none' })
  })

  it('edits a login JSON request using named fields and conceals its password', async () => {
    mountApi({ method: 'POST', json: { username: 'admin', password: 'synthetic-secret' } })
    const password = wrapper.get('input[aria-label="请求参数第 2 行参数值"]')
    expect(password.attributes('type')).toBe('password')
    await wrapper.get('input[aria-label="请求参数第 1 行参数值"]').setValue('monitor-user')
    expect(normalize().json).toEqual({ username: 'monitor-user', password: 'synthetic-secret' })
  })

  it('retains configured response validation, headers, auth and TLS settings while collapsed', () => {
    const config = {
      method: 'POST', expected_status: [200, 201], json: { username: 'admin', password: 'synthetic' },
      headers: { Authorization: '********', 'Content-Type': 'application/json' },
      auth: { type: 'bearer', token: '********' }, follow_redirects: false, verify_tls: false,
      keywords: ['token'], regex: '"token"', json_assertions: [{ path: '$.user.username', value: 'admin' }],
      max_body_bytes: 131072,
    }
    mountApi(config)
    expect(wrapper.text()).toContain('已配置')
    expect(normalize()).toEqual(config)
  })

  it('preserves numeric, boolean, null and nested JSON values in text mode', () => {
    const json = { count: 3, enabled: true, nested: { x: [1, null] } }
    mountApi({ method: 'POST', json })
    expect(wrapper.find('textarea[aria-label="请求内容文本"]').exists()).toBe(true)
    expect(normalize().json).toEqual(json)
  })

  it('keeps form requests as form requests', () => {
    mountApi({ method: 'POST', form: { username: 'monitor', password: 'synthetic' } })
    const value = normalize()
    expect(value.form).toEqual({ username: 'monitor', password: 'synthetic' })
    expect(value.json).toBeUndefined()
  })

  it('preserves plain text and GET requests that already contain a body', () => {
    mountApi({ method: 'GET', body: 'ping\r\n正文' })
    expect(normalize().body).toBe('ping\r\n正文')
  })

  it('retains non-string query values rather than coercing them into strings', () => {
    const params = { limit: 20, active: true, tags: ['one', 'two'] }
    mountApi({ params })
    expect(normalize().params).toEqual(params)
  })

  it('refreshes the editor when moving between tasks of the same API type', async () => {
    mountApi({ method: 'POST', json: { username: 'first' }, expected_status: [201] })
    await wrapper.setProps({ modelValue: { method: 'POST', body: 'second body', verify_tls: false, expected_status: [204] } })
    const value = normalize()
    expect(value.body).toBe('second body')
    expect(value.json).toBeUndefined()
    expect(value.expected_status).toEqual([204])
    expect(value.verify_tls).toBe(false)
  })

  it('does not add a JSON body when loading an existing POST task without one', async () => {
    mountApi({ method: 'GET' })
    await wrapper.setProps({ modelValue: { method: 'POST' } })
    await flushPromises()
    expect(normalize().json).toBeUndefined()
  })

  it('starts a JSON editor when the user selects POST for a new request', async () => {
    const config: Record<string, any> = { method: 'GET', auth: { type: 'none' } }
    mountApi(config)
    const method = wrapper.findAllComponents({ name: 'ElSelect' }).find(select => select.props('modelValue') === 'GET')!
    method.vm.$emit('update:modelValue', 'POST')
    await flushPromises()
    expect(normalize().json).toEqual({})
  })

  it('retains valid JSON text when changing from text to JSON', async () => {
    mountApi({ method: 'POST', body: '{"count":2,"enabled":true}' })
    const kind = wrapper.findAllComponents({ name: 'ElSelect' }).find(select => select.props('modelValue') === 'text')!
    kind.vm.$emit('update:modelValue', 'json')
    await flushPromises()
    expect(normalize().json).toEqual({ count: 2, enabled: true })
  })

  it('blocks invalid JSON instead of discarding it', async () => {
    mountApi({ method: 'POST', json: { count: 1 } })
    await wrapper.get('textarea[aria-label="请求内容文本"]').setValue('{broken')
    expect(() => normalize()).toThrow('请求内容必须是合法 JSON')
  })

  it('keeps invalid parameter rows when a format conversion cannot succeed', async () => {
    mountApi({ method: 'POST', json: { first: 'one', second: 'two' } })
    await wrapper.get('input[aria-label="请求参数第 2 行参数名"]').setValue('first')
    const kind = wrapper.findAllComponents({ name: 'ElSelect' }).find(select => select.props('modelValue') === 'json')!
    kind.vm.$emit('update:modelValue', 'text')
    await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('重复参数')
    expect(() => normalize()).toThrow('重复参数')
  })

  it('rejects header duplicates even when their case differs', () => {
    mountApi({ headers: { Authorization: 'first', authorization: 'second' } })
    expect(() => normalize()).toThrow('请求头名称不能重复')
  })

  it('continues validating custom status codes in advanced settings', async () => {
    mountApi({ expected_status: [201] })
    await wrapper.get('.el-collapse-item__header').trigger('click')
    const status = wrapper.findAll('.el-form-item').find(item => item.text().includes('期望状态码'))!
    await status.get('input').setValue('201, abc')
    expect(() => normalize()).toThrow('期望状态码')
  })

  it('keeps advanced JSON assertion paths and values exactly as configured', () => {
    mountApi({ json_assertions: [{ path: '$.status', value: false }] })
    expect(wrapper.findComponent(ApiMonitorConfigFields).exists()).toBe(true)
    expect(normalize().json_assertions).toEqual([{ path: '$.status', value: false }])
  })
})

describe('request field conversion', () => {
  it('refuses duplicate and unnamed parameters', () => {
    expect(() => fieldsObject([{ name: 'x', value: '1' }, { name: 'x', value: '2' }], '请求参数')).toThrow('重复')
    expect(() => fieldsObject([{ name: '', value: 'value' }], '请求参数')).toThrow('不能为空')
  })
  it('keeps meaningful whitespace and values and ignores empty placeholder rows', () => {
    expect(fieldsObject([{ name: ' key ', value: ' value ' }, { name: '', value: '' }], '请求参数')).toEqual({ ' key ': ' value ' })
    expect(fieldRows({})).toEqual([{ name: '', value: '' }])
    expect(isTextObject({ '': 'value' })).toBe(false)
  })
  it('does not mutate object prototypes through parameter names', () => {
    const value = fieldsObject([{ name: '__proto__', value: 'literal-value' }], '请求参数')
    expect(Object.prototype.hasOwnProperty.call(value, '__proto__')).toBe(true)
    expect(Object.getPrototypeOf(value)).toBe(Object.prototype)
  })
})
