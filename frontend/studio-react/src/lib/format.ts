export function formatDuration(value?: number | null) {
  return `${Number(value || 0).toFixed(2)}s`
}

export function formatBytes(value?: number | null) {
  const size = Number(value || 0)
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  if (size < 1024 * 1024 * 1024) return `${(size / (1024 * 1024)).toFixed(1)} MB`
  if (size < 1024 * 1024 * 1024 * 1024) return `${(size / (1024 * 1024 * 1024)).toFixed(1)} GB`
  return `${(size / (1024 * 1024 * 1024 * 1024)).toFixed(1)} TB`
}

export function compactId(value: string) {
  return value.slice(0, 8)
}
