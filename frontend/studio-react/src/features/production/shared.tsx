import { cloneElement, isValidElement, useId, type ReactNode } from 'react'
import { AlertTriangle, Loader2 } from 'lucide-react'
import { ApiError } from '@/lib/api'
import { Button } from '@/components/ui/button'

export const control = 'w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-950 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-100 disabled:bg-slate-50'
export const panel = 'rounded-lg border border-slate-200 bg-white p-4'

export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  const id = useId()
  const input = isValidElement<{ id?: string; 'aria-describedby'?: string }>(children) ? cloneElement(children, { id, 'aria-describedby': hint ? `${id}-hint` : undefined }) : children
  return <div className="block min-w-0"><label htmlFor={id} className="mb-1.5 block text-xs font-semibold text-slate-700">{label}</label>{input}{hint ? <span id={`${id}-hint`} className="mt-1 block text-xs text-slate-500">{hint}</span> : null}</div>
}

export function RequestError({ error, onReload }: { error: unknown; onReload?: () => void }) {
  if (!error) return null
  const conflict = error instanceof ApiError && error.status === 409
  return <div role="alert" className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-900">
    <div className="flex gap-2"><AlertTriangle className="mt-0.5 size-4 shrink-0" /><div>
      {conflict ? <p className="font-semibold">This request conflicts with the current server state. Review the details before retrying.</p> : null}
      <p>{error instanceof Error ? error.message : 'The request could not be completed.'}</p>
      {error instanceof ApiError && error.requestId ? <p className="mt-1 text-xs">Request: {error.requestId}</p> : null}
    </div></div>
    {onReload ? <Button variant="secondary" size="sm" className="mt-2" onClick={onReload}>Reload latest</Button> : null}
  </div>
}

export function Loading({ label = 'Loading' }: { label?: string }) {
  return <div role="status" className="flex items-center gap-2 p-5 text-sm text-slate-600"><Loader2 className="size-4 animate-spin" />{label}</div>
}

export function Empty({ title, children }: { title: string; children: ReactNode }) {
  return <div className="rounded-lg border border-dashed border-slate-300 p-8 text-center"><h3 className="font-semibold text-slate-900">{title}</h3><div className="mx-auto mt-2 max-w-lg text-sm text-slate-600">{children}</div></div>
}

export function Status({ value }: { value: string }) {
  const color = ['approved', 'succeeded', 'completed'].includes(value) ? 'bg-emerald-50 text-emerald-800' : ['failed', 'rejected', 'cancelled'].includes(value) ? 'bg-red-50 text-red-800' : 'bg-slate-100 text-slate-700'
  return <span className={`inline-flex rounded px-2 py-1 text-xs font-medium ${color}`}>{value.replaceAll('_', ' ')}</span>
}

export function Pager({ offset, total, size, onChange }: { offset: number; total: number; size: number; onChange: (offset: number) => void }) {
  return <div className="flex flex-wrap items-center justify-between gap-2 pt-3 text-xs text-slate-600"><span>{total ? `${offset + 1}–${Math.min(total, offset + size)} of ${total}` : 'No records'}</span><div className="flex gap-2"><Button size="sm" variant="secondary" disabled={offset === 0} onClick={() => onChange(Math.max(0, offset - size))}>Previous</Button><Button size="sm" variant="secondary" disabled={offset + size >= total} onClick={() => onChange(offset + size)}>Next</Button></div></div>
}
