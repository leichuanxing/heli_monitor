const path = require('node:path')
const { chromium } = require('playwright')

async function main() {
  const baseUrl = process.env.HELI_SCREENSHOT_URL
  const username = process.env.HELI_SCREENSHOT_USER
  const password = process.env.HELI_SCREENSHOT_PASSWORD
  if (!baseUrl || !username || !password) throw new Error('缺少截图登录环境变量')
  const browser = await chromium.launch({
    headless: true,
    executablePath: process.env.HELI_BROWSER_PATH,
  })
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
    await page.goto(`${baseUrl}/login`, { waitUntil: 'networkidle' })
    await page.locator('input').nth(0).fill(username)
    await page.locator('input').nth(1).fill(password)
    await Promise.all([
      page.waitForURL(`${baseUrl}/`),
      page.getByRole('button', { name: '登录系统' }).click(),
    ])
    await page.waitForLoadState('networkidle')
    await page.screenshot({ path: path.resolve('docs/homepage.png'), fullPage: true })
  } finally {
    await browser.close()
  }
}

main().catch(error => { console.error(error.message); process.exitCode = 1 })
