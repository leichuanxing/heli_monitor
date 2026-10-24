import { createApp } from 'vue'
import ElementPlus from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import 'element-plus/dist/index.css'
import 'element-plus/theme-chalk/dark/css-vars.css'
import App from './App.vue'
import router from './router'
import './styles.css'
import { initializeTheme } from './stores/theme'
initializeTheme()
createApp(App).use(ElementPlus, { locale: zhCn }).use(router).mount('#app')
