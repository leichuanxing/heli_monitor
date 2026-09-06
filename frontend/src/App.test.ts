import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import App from './App.vue'
describe('App', () => { it('renders the active route outlet', () => { expect(mount(App, { global: { stubs: { RouterView: { template: '<div>route</div>' } } } }).text()).toBe('route') }) })
