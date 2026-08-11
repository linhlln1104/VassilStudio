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
        'inline-flex h-9 min-w-0 gap-0.5 rounded-lg border border-neutral-200 bg-neutral-100 p-0.5',
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
              'inline-flex h-[30px] items-center justify-center whitespace-nowrap rounded-md px-3 text-xs font-medium leading-none text-neutral-600 transition-colors',
              equalWidth ? 'min-w-0 flex-1' : 'shrink-0',
              option.value === value
                ? 'bg-white text-blue-700 ring-1 ring-inset ring-neutral-200'
                : 'hover:bg-white/70 hover:text-neutral-950',
              itemDisabled && 'cursor-not-allowed opacity-60 hover:bg-transparent hover:text-neutral-600',
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
