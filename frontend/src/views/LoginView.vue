<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import client from '../api/client'

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
  <div class="login">
    <div class="login-shell">
      <section class="welcome">
        <span>{{branding.login_page_description}}</span>
        <h2>让业务运行状态清晰可见</h2>
        <p>统一监控业务可用性、服务性能、故障事件与告警通知。</p>
      </section>
      <el-card shadow="never">
        <div class="form-heading"><small>欢迎登录</small><h1>{{branding.home_page_title}}</h1><p>请输入系统账号和密码</p></div>
        <el-form @submit.prevent="login">
          <el-form-item><el-input v-model="username" placeholder="用户名" size="large" /></el-form-item>
          <el-form-item><el-input v-model="password" type="password" show-password placeholder="密码" size="large" @keyup.enter="login" /></el-form-item>
          <el-button type="primary" size="large" :loading="loading" @click="login">登录系统</el-button>
        </el-form>
      </el-card>
    </div>
  </div>
</template>

<style scoped>
.login{min-height:100vh;display:grid;place-items:center;padding:24px;background:radial-gradient(circle at 18% 18%,#155779 0,transparent 32%),linear-gradient(135deg,#06182b,#0a4058 62%,#087067)}.login-shell{width:min(880px,94vw);display:grid;grid-template-columns:1.05fr .95fr;overflow:hidden;border:1px solid #ffffff20;border-radius:14px;box-shadow:0 28px 70px #020e1966}.welcome{min-height:430px;padding:52px 48px;display:flex;flex-direction:column;align-items:flex-start;justify-content:center;color:#fff;background:linear-gradient(145deg,#0a2d49e8,#07525be8)}.welcome :deep(.brand-logo){width:auto;justify-content:flex-start;margin-bottom:54px}.welcome>span{font-size:10px;letter-spacing:.25em;color:#6dd5e4}.welcome h2{font-size:28px;margin:14px 0 12px}.welcome p{max-width:330px;margin:0;color:#aad0d8;line-height:1.8}.el-card{border:0;border-radius:0;display:grid;align-items:center;padding:40px 35px;background:#fff}.form-heading{margin-bottom:28px}.form-heading small{color:#247496;font-weight:650}.form-heading h1{font-size:25px;line-height:1.35;color:#172d43;margin:8px 0}.form-heading p{font-size:13px;color:#8a98a7;margin:0}.el-button{width:100%;margin-top:5px}@media(max-width:720px){.login-shell{grid-template-columns:1fr}.welcome{display:none}.el-card{min-height:430px;padding:38px 28px}}
</style>
