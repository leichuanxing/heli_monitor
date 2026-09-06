<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import client from '../api/client'
import BrandLogo from '../components/BrandLogo.vue'
import { loadSystemSettings, systemSettings } from '../stores/systemSettings'

const loading = ref(false)
const saving = ref(false)
const form = ref({
  brand_logo_text: '合力数据',
  home_page_title: '合力数据业务监控系统',
  browser_title: '合力数据业务监控系统',
  login_page_description: '企业级业务可用性监控与告警平台',
  monitor_wall_title: '合力数据业务监控系统',
  dashboard_refresh_seconds: 30,
  monitor_wall_refresh_seconds: 10,
  monitor_result_retention_count: 10000,
})

async function load() {
  loading.value = true
  try {
    await loadSystemSettings()
    form.value = {
      brand_logo_text: systemSettings.brand_logo_text,
      home_page_title: systemSettings.home_page_title,
      browser_title: systemSettings.browser_title,
      login_page_description: systemSettings.login_page_description,
      monitor_wall_title: systemSettings.monitor_wall_title,
      dashboard_refresh_seconds: systemSettings.dashboard_refresh_seconds,
      monitor_wall_refresh_seconds: systemSettings.monitor_wall_refresh_seconds,
      monitor_result_retention_count: systemSettings.monitor_result_retention_count,
    }
  } catch (error: any) {
    ElMessage.error(error.response?.data?.message || '系统设置加载失败')
  } finally {
    loading.value = false
  }
}

async function save() {
  saving.value = true
  try {
    const { data } = await client.patch('/system/settings/', form.value)
    Object.assign(systemSettings, data)
    document.title = systemSettings.browser_title
    ElMessage.success('系统设置已保存并即时生效')
  } catch (error: any) {
    const details = error.response?.data?.details || error.response?.data
    const message = typeof details === 'object' ? Object.values(details || {})[0] : details
    ElMessage.error(String(message || '系统设置保存失败'))
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="heading"><div><h2>系统设置</h2><p>应用品牌与监控大屏显示设置</p></div><el-button :loading="loading" @click="load">重新加载</el-button></div>
  <el-card shadow="never">
    <template #header><div class="title"><b>品牌显示</b><span>仅使用文本 Logo，不上传图片文件</span></div></template>
    <el-form label-position="top" class="settings-form">
      <el-form-item label="左上角 Logo 文本"><el-input v-model="form.brand_logo_text" maxlength="32" show-word-limit placeholder="例如：合力数据"/><small>显示在应用左侧导航顶部；菜单折叠后显示第一个字符。</small></el-form-item>
      <div class="preview"><span>显示预览</span><div><BrandLogo theme="dark" :text="form.brand_logo_text || '合力数据'"/></div></div>
      <el-form-item label="首页标题"><el-input v-model="form.home_page_title" maxlength="64" show-word-limit placeholder="例如：合力数据业务监控系统"/><small>显示在用户登录页的登录表单上方。</small></el-form-item>
      <el-form-item label="登录页说明"><el-input v-model="form.login_page_description" maxlength="128" show-word-limit placeholder="例如：企业级业务可用性监控与告警平台"/><small>显示在登录页左侧的产品说明区域。</small></el-form-item>
      <el-form-item label="浏览器标题"><el-input v-model="form.browser_title" maxlength="64" show-word-limit placeholder="例如：合力数据业务监控系统"/><small>保存后更新浏览器标签页标题。</small></el-form-item>
      <el-form-item label="监控大屏标题"><el-input v-model="form.monitor_wall_title" maxlength="64" show-word-limit placeholder="例如：合力数据业务监控系统"/><small>显示在监控大屏顶部中心位置。</small></el-form-item>
      <el-divider content-position="left">刷新与数据保留</el-divider>
      <el-row :gutter="18">
        <el-col :span="8"><el-form-item label="监控总览刷新周期"><el-input-number v-model="form.dashboard_refresh_seconds" :min="5" :max="300" controls-position="right"/><small>单位：秒，范围 5–300。</small></el-form-item></el-col>
        <el-col :span="8"><el-form-item label="监控大屏刷新周期"><el-input-number v-model="form.monitor_wall_refresh_seconds" :min="5" :max="300" controls-position="right"/><small>WebSocket 之外的兜底同步周期，单位：秒。</small></el-form-item></el-col>
        <el-col :span="8"><el-form-item label="单任务探测结果保留数"><el-input-number v-model="form.monitor_result_retention_count" :min="100" :max="1000000" :step="1000" controls-position="right"/><small>每个探测任务独立保留，范围 100–1,000,000。</small></el-form-item></el-col>
      </el-row>
      <el-button type="primary" :loading="saving" :disabled="!systemSettings.can_manage" @click="save">保存设置</el-button>
      <el-alert v-if="!systemSettings.can_manage" class="permission-tip" title="当前账号只有查看权限，修改设置需要“系统维护”权限" type="info" :closable="false"/>
    </el-form>
  </el-card>
</template>

<style scoped>
.heading{display:flex;justify-content:space-between;align-items:center;margin-bottom:16px}.heading h2{margin:0;color:#192c42}.heading p{margin:5px 0 0;color:#7b8a9c}.title{display:flex;align-items:end;gap:12px}.title span,.settings-form small{font-size:12px;color:#8593a3}.settings-form{max-width:760px}.settings-form small{display:block;margin-top:6px}.preview{margin:-4px 0 20px}.preview>span{display:block;font-size:12px;color:#68798b;margin-bottom:7px}.preview>div{width:248px;height:72px;display:flex;align-items:center;padding:0 17px;background:linear-gradient(180deg,#071d31,#0a2943);border-radius:6px}.permission-tip{margin-top:16px}
</style>
