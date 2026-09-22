import { useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, RefreshCw } from 'lucide-react'
import type { ReactNode } from 'react'

import { Button } from '@/components/ui/button'
import { api } from '@/lib/api'
import { authPageUrl } from '@/lib/auth-navigation'
import { BRAND_LOGO_SRC, BRAND_NAME } from '@/lib/brand'

type AuthGateProps = {
  children: ReactNode
}

export function AuthGate({ children }: AuthGateProps) {
  const statusQuery = useQuery({
    queryKey: ['auth-status'],
    queryFn: api.authStatus,
    refetchOnWindowFocus: true,
  })

  useEffect(() => {
    const status = statusQuery.data
    if (!status?.auth_required) {
      return
    }
    if (status.setup_required) {
      window.location.assign(authPageUrl('setup'))
      return
    }
    if (!status.authenticated) {
      window.location.assign(authPageUrl('login'))
    }
  }, [statusQuery.data])

  if (statusQuery.isLoading) {
    return <AuthLoadingScreen />
  }

  if (statusQuery.isError) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-white px-4 text-slate-950">
        <div className="w-full max-w-sm rounded-md border border-slate-200 bg-white p-4">
          <div className="flex items-center gap-2 text-sm font-semibold">
            <AlertTriangle className="size-4 text-red-600" />
            Session check failed
          </div>
          <p className="mt-1 text-xs leading-5 text-slate-600">
            The local API did not return authentication status.
          </p>
          <Button className="mt-4" size="sm" variant="secondary" onClick={() => { void statusQuery.refetch() }}>
            <RefreshCw className="size-4" />
            Retry
          </Button>
        </div>
      </div>
    )
  }

  if (statusQuery.data?.auth_required && !statusQuery.data.authenticated) {
    return <AuthLoadingScreen />
  }

  return children
}

function AuthLoadingScreen() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-white px-4">
      <div className="w-full max-w-sm rounded-md border border-slate-200 bg-white p-4" aria-label="Checking workspace session">
        <img className="h-7 w-auto" src={BRAND_LOGO_SRC} alt={BRAND_NAME} />
        <div className="mt-4 h-3 w-24 animate-pulse rounded bg-slate-100" />
        <div className="mt-3 h-8 animate-pulse rounded-md bg-slate-100" />
        <div className="mt-2 h-8 animate-pulse rounded-md bg-slate-100" />
      </div>
    </div>
  )
}
