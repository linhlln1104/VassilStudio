import { Slot } from '@radix-ui/react-slot'
import { cva, type VariantProps } from 'class-variance-authority'
import type { ButtonHTMLAttributes } from 'react'

import { cn } from '@/lib/utils'

const buttonVariants = cva(
  'inline-flex items-center justify-center gap-1.5 whitespace-nowrap rounded-md text-[13px] font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[rgb(var(--ring))] focus-visible:ring-offset-2 focus-visible:ring-offset-white disabled:pointer-events-none disabled:opacity-55',
  {
    variants: {
      variant: {
        default:
          'bg-studio-sapphire text-white shadow-[0_1px_2px_rgba(0,0,0,0.08)] hover:bg-blue-800 disabled:bg-neutral-300 disabled:text-neutral-600 disabled:shadow-none',
        secondary:
          'border border-neutral-300 bg-white text-neutral-900 hover:border-neutral-400 hover:bg-neutral-50 disabled:bg-white disabled:text-neutral-400',
        ghost: 'text-neutral-600 hover:bg-neutral-100 hover:text-neutral-950 disabled:bg-transparent disabled:text-neutral-400',
        subtle:
          'border border-blue-100 bg-blue-50 text-blue-700 hover:border-blue-200 hover:bg-blue-100 disabled:bg-neutral-100 disabled:text-neutral-400',
        destructive: 'bg-red-700 text-white hover:bg-red-800 disabled:bg-neutral-300 disabled:text-neutral-600',
      },
      size: {
        default: 'h-9 px-3.5 py-2',
        sm: 'h-8 px-3 text-xs',
        lg: 'h-10 px-4 text-sm',
        icon: 'size-9',
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
