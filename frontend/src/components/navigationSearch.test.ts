import { describe, expect, it } from 'vitest'
import { searchNavigation } from './navigationSearch'
const items = [{path:'/monitors',title:'探测任务',group:'监控中心'}, {path:'/incidents',title:'故障事件',group:'事件与告警'}]
describe('navigation search', () => {
  it('matches module and page terms together', () => { expect(searchNavigation(items,'监控 探测')).toEqual([items[0]]) })
  it('supports paths without case sensitivity', () => { expect(searchNavigation(items,'INCIDENTS')).toEqual([items[1]]) })
  it('only returns supplied accessible items and handles empty searches', () => { expect(searchNavigation([items[0]],'告警')).toEqual([]); expect(searchNavigation(items,'  ')).toEqual(items) })
})
