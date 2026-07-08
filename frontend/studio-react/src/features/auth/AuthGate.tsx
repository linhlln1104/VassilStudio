import { useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import type { ReactNode } from 'react'

import { api } from '@/lib/api'

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
      window.location.assign('/setup')
      return
    }
    if (!status.authenticated) {
      window.location.assign('/login')
    }
  }, [statusQuery.data])

  if (statusQuery.isLoading) {
    return <AuthLoadingScreen />
  }

  if (statusQuery.isError) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-white px-4 text-slate-950">
        <div className="w-full max-w-sm rounded-md border border-slate-200 bg-white p-4">
          <div className="text-sm font-semibold">Session check failed</div>
          <p className="mt-1 text-xs leading-5 text-slate-600">
            Refresh the page after the API is reachable.
          </p>
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
      <div className="w-full max-w-sm rounded-md border border-slate-200 bg-white p-4">
        <div className="h-3 w-24 animate-pulse rounded bg-slate-100" />
        <div className="mt-3 h-8 animate-pulse rounded-md bg-slate-100" />
        <div className="mt-2 h-8 animate-pulse rounded-md bg-slate-100" />
      </div>
    </div>
  )
}
