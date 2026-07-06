import { cn } from '@/lib/utils'

export type SegmentedOption<T extends string> = {
  value: T
  label: string
  title?: string
  disabled?: boolean
}

export type SegmentedControlProps<T extends string> = {
  options: Array<SegmentedOption<T>>
  value: T
  onChange: (value: T) => void
  disabled?: boolean
  equalWidth?: boolean
  className?: string
  itemClassName?: string
}

export function SegmentedControl<T extends string>({
  options,
  value,
  onChange,
  disabled = false,
  equalWidth = false,
  className,
  itemClassName,
}: SegmentedControlProps<T>) {
  return (
    <div
      className={cn(
        'inline-flex h-8 min-w-0 overflow-hidden rounded-md border border-slate-200 bg-white',
        equalWidth && 'w-full',
        className,
      )}
    >
      {options.map((option) => {
        const itemDisabled = disabled || option.disabled

        return (
          <button
            key={option.value}
            type="button"
            aria-pressed={option.value === value}
            className={cn(
              'inline-flex h-8 items-center justify-center whitespace-nowrap border-r border-slate-200 px-3 text-xs font-medium leading-none text-slate-600 transition-colors last:border-r-0',
              equalWidth ? 'min-w-0 flex-1' : 'shrink-0',
              option.value === value
                ? 'bg-sky-50 text-blue-700'
                : 'hover:bg-slate-50 hover:text-slate-950',
              itemDisabled && 'cursor-not-allowed opacity-60 hover:bg-white hover:text-slate-600',
              itemClassName,
            )}
            title={option.title}
            disabled={itemDisabled}
            onClick={() => onChange(option.value)}
          >
            {option.label}
          </button>
        )
      })}
    </div>
  )
}
