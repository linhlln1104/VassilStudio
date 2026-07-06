import { createContext, useContext } from 'react'

export type ToastVariant = 'success' | 'danger' | 'info'

export type ToastItem = {
  id: number
  title: string
  description?: string
  variant: ToastVariant
}

export type ToastInput = Omit<ToastItem, 'id' | 'variant'> & {
  variant?: ToastVariant
}

export type ToastContextValue = {
  toast: (toast: ToastInput) => void
}

export const ToastContext = createContext<ToastContextValue | null>(null)

export function useToast() {
  const value = useContext(ToastContext)
  if (!value) {
    throw new Error('useToast must be used inside ToastProvider')
  }
  return value
}
