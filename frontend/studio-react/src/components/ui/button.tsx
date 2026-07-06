import { Slot } from '@radix-ui/react-slot'
import { cva, type VariantProps } from 'class-variance-authority'
import type { ButtonHTMLAttributes } from 'react'

import { cn } from '@/lib/utils'

const buttonVariants = cva(
  'inline-flex items-center justify-center gap-1.5 whitespace-nowrap rounded-[6px] text-xs font-medium shadow-none transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[rgb(var(--ring))] focus-visible:ring-offset-1 disabled:pointer-events-none disabled:opacity-100',
  {
    variants: {
      variant: {
        default:
          'bg-gradient-to-r from-sky-500 via-blue-600 to-violet-600 text-white hover:brightness-105 disabled:bg-none disabled:bg-slate-200 disabled:text-slate-500 disabled:brightness-100',
        secondary:
          'border border-slate-200 bg-white text-slate-900 hover:border-sky-200 hover:bg-sky-50/40 disabled:bg-white disabled:text-slate-400',
        ghost: 'text-slate-700 hover:bg-slate-50 hover:text-slate-950 disabled:bg-transparent disabled:text-slate-400',
        subtle:
          'border border-sky-100 bg-[rgb(var(--accent))] text-[rgb(var(--accent-foreground))] hover:bg-sky-50 disabled:bg-slate-100 disabled:text-slate-400',
        destructive: 'bg-[rgb(var(--destructive))] text-white hover:bg-red-700 disabled:bg-slate-200 disabled:text-slate-500',
      },
      size: {
        default: 'h-8 px-3 py-1.5',
        sm: 'h-7 px-2.5 text-xs',
        lg: 'h-9 px-3.5',
        icon: 'h-8 w-8',
      },
    },
    defaultVariants: {
      variant: 'default',
      size: 'default',
    },
  },
)

export type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> &
  VariantProps<typeof buttonVariants> & {
    asChild?: boolean
  }

export function Button({ className, variant, size, asChild = false, ...props }: ButtonProps) {
  const Comp = asChild ? Slot : 'button'
  return <Comp className={cn(buttonVariants({ variant, size, className }))} {...props} />
}
