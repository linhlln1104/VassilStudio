export type ImportTable = { columns: string[]; records: Array<Record<string, string>> }

export function parseBatchImport(source: string): ImportTable {
  const text = source.replace(/^\uFEFF/, '').trim()
  if (!text) throw new Error('Choose a CSV or JSON file containing script rows.')
  if (text.startsWith('[')) {
    const rows: unknown = JSON.parse(text)
    if (!Array.isArray(rows) || !rows.length || rows.length > 5000) throw new Error('JSON must contain 1–5,000 row objects.')
    const columns: string[] = []
    const records = rows.map((row, index) => {
      if (!row || typeof row !== 'object' || Array.isArray(row)) throw new Error(`JSON row ${index + 1} must be an object.`)
      const record: Record<string, string> = {}
      for (const [key, value] of Object.entries(row)) {
        if (value !== null && !['string', 'number', 'boolean'].includes(typeof value)) throw new Error(`Row ${index + 1}: ${key} must be a plain value.`)
        if (!columns.includes(key)) columns.push(key)
        record[key] = value == null ? '' : String(value)
      }
      return record
    })
    return { columns, records }
  }
  const rows: string[][] = []
  let row: string[] = [], cell = '', quoted = false
  for (let i = 0; i < text.length; i++) {
    const char = text[i]
    if (char === '"') {
      if (quoted && text[i + 1] === '"') { cell += '"'; i++ }
      else if (!quoted && cell.trim()) throw new Error('Invalid CSV quote. Quote the entire field when it contains commas.')
      else quoted = !quoted
    } else if (!quoted && char === ',') { row.push(cell); cell = '' }
    else if (!quoted && (char === '\n' || char === '\r')) {
      if (char === '\r' && text[i + 1] === '\n') i++
      row.push(cell); if (row.some((value) => value.trim())) rows.push(row); row = []; cell = ''
    } else cell += char
  }
  if (quoted) throw new Error('CSV contains an unclosed quoted field.')
  row.push(cell); if (row.some((value) => value.trim())) rows.push(row)
  const columns = rows.shift()?.map((value) => value.trim()) ?? []
  if (!columns.length || columns.some((column) => !column) || new Set(columns).size !== columns.length) throw new Error('CSV requires nonempty, unique column headers.')
  if (!rows.length || rows.length > 5000) throw new Error('Import must contain 1–5,000 data rows.')
  return { columns, records: rows.map((values, index) => {
    if (values.length !== columns.length) throw new Error(`CSV row ${index + 2} has ${values.length} columns; expected ${columns.length}.`)
    return Object.fromEntries(columns.map((column, i) => [column, values[i]]))
  }) }
}
