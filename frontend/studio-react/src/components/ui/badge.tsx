import type { HTMLAttributes } from 'react'

import { cn } from '@/lib/utils'

type BadgeVariant = 'default' | 'success' | 'warning' | 'danger' | 'muted'

const variants: Record<BadgeVariant, string> = {
  default: 'border-slate-200 bg-white text-slate-700',
  success: 'border-sky-200 bg-white text-blue-700',
  warning: 'border-amber-200 bg-white text-amber-700',
  danger: 'border-red-200 bg-white text-red-700',
  muted: 'border-slate-200 bg-white text-slate-600',
}

export function Badge({
  className,
  variant = 'default',
  ...props
}: HTMLAttributes<HTMLSpanElement> & { variant?: BadgeVariant }) {
  return (
    <span
      className={cn(
        'inline-flex min-h-5 items-center rounded-[5px] border px-2 text-xs font-medium',
        variants[variant],
        className,
      )}
      {...props}
    />
  )
}
