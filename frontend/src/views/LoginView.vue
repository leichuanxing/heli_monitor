<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import client from '../api/client'
import BrandLogo from '../components/BrandLogo.vue'
import ThemeToggle from '../components/ThemeToggle.vue'
import { theme } from '../stores/theme'

const router = useRouter()
const username = ref('')
const password = ref('')
const loading = ref(false)
const branding = ref({ brand_logo_text: '合力数据', home_page_title: '合力数据业务监控系统', browser_title: '合力数据业务监控系统', login_page_description: '企业级业务可用性监控与告警平台' })

async function loadBranding() {
  try {
    branding.value = (await client.get('/public/branding/')).data
    document.title = branding.value.browser_title
  } catch {
    // 后端暂不可用时使用内置品牌信息，确保登录入口仍可展示。
  }
}

async function login() {
  loading.value = true
  try {
    const { data } = await client.post('/auth/login/', {
      username: username.value,
      password: password.value,
    })
    localStorage.setItem('access_token', data.access)
    localStorage.setItem('refresh_token', data.refresh)
    router.push('/')
  } catch {
    ElMessage.error('用户名或密码错误')
  } finally {
    loading.value = false
  }
}

onMounted(loadBranding)
</script>

<template>
  <div class="login"><div class="login-theme"><ThemeToggle/></div>
    <div class="login-shell">
      <section class="welcome"><BrandLogo :theme="theme" :text="branding.brand_logo_text"/><div class="welcome-eyebrow">BUSINESS OBSERVABILITY</div>
        <span>{{branding.login_page_description}}</span>
        <h2>让业务运行状态清晰可见</h2>
        <p>统一监控业务可用性、服务性能、故障事件与告警通知。</p>
      </section>
      <el-card shadow="never">
        <div class="form-heading"><small>欢迎登录</small><h1>{{branding.home_page_title}}</h1><p>请输入系统账号和密码</p></div>
        <el-form @submit.prevent="login">
          <el-form-item><el-input v-model="username" aria-label="用户名" autocomplete="username" placeholder="用户名" size="large" /></el-form-item>
          <el-form-item><el-input v-model="password" aria-label="密码" autocomplete="current-password" type="password" show-password placeholder="密码" size="large" @keyup.enter="login" /></el-form-item>
          <el-button type="primary" size="large" :loading="loading" @click="login">登录系统</el-button>
        </el-form>
      </el-card>
    </div>
  </div>
</template>

<style scoped>
.login{min-height:100dvh;display:grid;place-items:center;padding:40px 24px;background:var(--canvas)}.login-theme{position:fixed;right:28px;top:24px}.login-shell{width:min(980px,100%);display:grid;grid-template-columns:1.05fr 1fr;border:1px solid var(--border);background:var(--surface);border-radius:20px;overflow:hidden;box-shadow:0 12px 50px #15294a08}.welcome{min-height:540px;padding:48px 42px;display:flex;flex-direction:column;align-items:flex-start;justify-content:center;background:var(--brand-soft);color:var(--text-primary)}.welcome :deep(.brand-logo){margin-bottom:70px}.welcome-eyebrow{font-size:10px;letter-spacing:.16em;color:var(--brand);font-weight:650;margin-bottom:10px}.welcome>span{font-size:12px;color:var(--text-secondary)}.welcome h2{font-size:30px;line-height:1.6;letter-spacing:-.04em;margin:16px 0;color:var(--text-primary)}.welcome p{font-size:13px;line-height:1.9;color:var(--muted);max-width:320px;margin:0}.el-card{border:0!important;border-radius:0!important;box-shadow:none!important;display:grid;align-items:center;padding:36px 24px;background:var(--surface)}.form-heading{margin-bottom:32px}.form-heading small{color:var(--brand);font-size:12px;font-weight:600}.form-heading h1{font-size:22px;letter-spacing:-.025em;line-height:1.5;color:var(--text-primary);margin:10px 0}.form-heading p{font-size:12px;color:var(--muted);margin:0}.el-button{width:100%;margin-top:8px;height:42px}.el-form-item{margin-bottom:20px}@media(max-width:720px){.login{padding:70px 16px 24px}.login-shell{grid-template-columns:1fr;max-width:460px}.welcome{min-height:0;padding:26px 28px}.welcome :deep(.brand-logo){margin-bottom:22px}.welcome h2{font-size:23px;margin:8px 0}.welcome-eyebrow,.welcome p{display:none}.el-card{padding:24px 12px}.login-theme{top:18px;right:18px}}
</style>
