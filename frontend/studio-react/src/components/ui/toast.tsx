import {
  useCallback,
  useMemo,
  useState,
  type PropsWithChildren,
} from 'react'
import { CheckCircle2, Info, X, XCircle } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { ToastContext, type ToastInput, type ToastItem } from '@/components/ui/use-toast'
import { cn } from '@/lib/utils'

export function ToastProvider({ children }: PropsWithChildren) {
  const [toasts, setToasts] = useState<ToastItem[]>([])

  const dismiss = useCallback((id: number) => {
    setToasts((items) => items.filter((item) => item.id !== id))
  }, [])

  const toast = useCallback(
    (input: ToastInput) => {
      const id = Date.now() + Math.floor(Math.random() * 1000)
      const item: ToastItem = {
        id,
        title: input.title,
        description: input.description,
        variant: input.variant ?? 'info',
      }
      setToasts((items) => [item, ...items].slice(0, 4))
      window.setTimeout(() => dismiss(id), 4500)
    },
    [dismiss],
  )

  const value = useMemo(() => ({ toast }), [toast])

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="fixed bottom-4 right-4 z-50 flex w-[min(420px,calc(100vw-32px))] flex-col gap-2">
        {toasts.map((item) => (
          <ToastCard key={item.id} item={item} onDismiss={() => dismiss(item.id)} />
        ))}
      </div>
    </ToastContext.Provider>
  )
}

function ToastCard({ item, onDismiss }: { item: ToastItem; onDismiss: () => void }) {
  const Icon = item.variant === 'success' ? CheckCircle2 : item.variant === 'danger' ? XCircle : Info

  return (
    <div
      className={cn(
        'flex items-start gap-2 rounded-md border bg-white p-3 shadow-md',
        item.variant === 'success' && 'border-sky-200',
        item.variant === 'danger' && 'border-red-200',
        item.variant === 'info' && 'border-slate-200',
      )}
    >
      <Icon
        className={cn(
          'mt-0.5 size-5 shrink-0',
          item.variant === 'success' && 'text-blue-600',
          item.variant === 'danger' && 'text-red-600',
          item.variant === 'info' && 'text-slate-600',
        )}
      />
      <div className="min-w-0 flex-1">
        <div className="text-sm font-semibold text-slate-950">{item.title}</div>
        {item.description ? (
          <div className="mt-1 text-xs font-medium leading-5 text-slate-600">{item.description}</div>
        ) : null}
      </div>
      <Button aria-label="Dismiss notification" size="icon" variant="ghost" onClick={onDismiss}>
        <X className="size-4" />
      </Button>
    </div>
  )
}
