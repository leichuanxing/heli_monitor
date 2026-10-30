export interface RequestField { name: string; value: string }

export function isTextObject(value: unknown): value is Record<string, string> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    && Object.entries(value).every(([name, item]) => !!name.trim() && typeof item === 'string')
}

export function fieldRows(value?: Record<string, string>): RequestField[] {
  const rows = Object.entries(value || {}).map(([name, item]) => ({ name, value: item }))
  return rows.length ? rows : [{ name: '', value: '' }]
}

export function fieldsObject(rows: RequestField[], label: string, trimNames = false): Record<string, string> {
  const seen = new Set<string>()
  const entries: [string, string][] = []
  for (const row of rows) {
    if (!row.name.trim() && !row.value) continue
    const name = trimNames ? row.name.trim() : row.name
    if (!name.trim()) throw new Error(`${label}的参数名不能为空`)
    if (seen.has(name)) throw new Error(`${label}存在重复参数：${name}`)
    seen.add(name)
    entries.push([name, row.value])
  }
  return Object.fromEntries(entries)
}
