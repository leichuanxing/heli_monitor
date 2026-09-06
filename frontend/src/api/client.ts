import axios from 'axios'

const client = axios.create({ baseURL: '/api/v1', timeout: 20000 })
let refreshing: Promise<string> | null = null

function clearSession() {
  localStorage.removeItem('access_token')
  localStorage.removeItem('refresh_token')
}

client.interceptors.request.use(config => {
  const token = localStorage.getItem('access_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

client.interceptors.response.use(response => response, async error => {
  const config = error.config
  if (error.response?.status !== 401 || !config || config._retry || config.url?.startsWith('/auth/')) {
    return Promise.reject(error)
  }
  config._retry = true
  const refresh = localStorage.getItem('refresh_token')
  if (!refresh) {
    clearSession()
    location.assign('/login')
    return Promise.reject(error)
  }
  try {
    if (!refreshing) {
      refreshing = axios.post('/api/v1/auth/refresh/', { refresh }, { timeout: 20000 })
        .then(({ data }) => {
          if (localStorage.getItem('refresh_token') !== refresh) throw new Error('登录状态已变更')
          localStorage.setItem('access_token', data.access)
          if (data.refresh) localStorage.setItem('refresh_token', data.refresh)
          return data.access as string
        }).finally(() => { refreshing = null })
    }
    await refreshing
  } catch (refreshError) {
    clearSession()
    location.assign('/login')
    return Promise.reject(refreshError)
  }
  return client(config)
})

export default client
