import { theme } from '../stores/theme'

export const chartColors = ['#2870e8', '#19a183', '#8a67d9', '#de9136', '#dc6271', '#259bb7', '#7184a1', '#bf70b1']

export function chartAppearance(mode?: 'light' | 'dark') {
  const dark = (mode ?? theme.value) === 'dark'
  const text = dark ? '#a5b4c9' : '#62738c'
  const border = dark ? '#2b3c54' : '#e7edf5'
  return {
    animation: false,
    color: dark ? ['#79a8ff', '#59c6a4', '#b49aef', '#e7b56f', '#ef94a6', '#64bfd5', '#a3b4ce', '#d69bc9'] : chartColors,
    backgroundColor: 'transparent',
    textStyle: { color: text, fontFamily: 'Inter, Segoe UI, Microsoft YaHei, sans-serif', fontSize: 11 },
    tooltip: { backgroundColor: dark ? '#1c2a3d' : '#ffffff', borderColor: border, borderWidth: 1, padding: [10, 14], textStyle: { color: dark ? '#e8eef7' : '#24354c', fontSize: 12 }, extraCssText: 'border-radius:8px;box-shadow:0 4px 18px #071d3114;' },
    xAxis: { axisLine: { lineStyle: { color: border } }, axisTick: { show: false }, axisLabel: { color: text, hideOverlap: true }, splitLine: { show: false } },
    yAxis: { axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: text }, nameTextStyle: { color: text }, splitLine: { lineStyle: { color: border, type: 'dashed' as const } } },
  }
}
