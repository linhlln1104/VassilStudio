import { AlertTriangle, RefreshCw } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

type QueryErrorStateProps = {
  title: string
  message: string
  onRetry: () => void
  compact?: boolean
}

export function QueryErrorState({ title, message, onRetry, compact = false }: QueryErrorStateProps) {
  return (
    <div
      className={cn(
        'rounded-md border border-red-200 bg-red-50 text-center',
        compact ? 'p-3' : 'p-4',
      )}
    >
      <AlertTriangle className="mx-auto size-7 text-red-600" />
      <div className="mt-2 text-sm font-semibold text-red-950">{title}</div>
      <p className="mx-auto mt-1 max-w-md text-xs leading-5 text-red-800">{message}</p>
      <Button className="mt-3" size="sm" variant="secondary" onClick={onRetry}>
        <RefreshCw className="size-4" />
        Retry
      </Button>
    </div>
  )
}
