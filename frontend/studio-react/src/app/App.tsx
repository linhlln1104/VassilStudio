import { Suspense, useCallback, useEffect, useMemo, useState } from 'react'

import { AppShell } from '@/components/app-shell/AppShell'
import { AuthGate } from '@/features/auth/AuthGate'
import { AuthPage } from '@/features/auth/AuthPage'
import { ProductShell } from '@/features/product/ProductShell'

import { AppProviders } from './providers'
import { RouteErrorBoundary } from './RouteErrorBoundary'
import { routeFromHash, routes, type RouteId } from './routes'

type ProductPage = 'privacy' | 'license' | 'support' | 'changelog' | 'operations'

function StudioApp() {
  const [activeRoute, setActiveRoute] = useState<RouteId>(() => routeFromHash(window.location.hash))

  useEffect(() => {
    const handleHashChange = () => setActiveRoute(routeFromHash(window.location.hash))
    window.addEventListener('hashchange', handleHashChange)
    return () => window.removeEventListener('hashchange', handleHashChange)
  }, [])

  const ActiveView = useMemo(
    () => routes.find((route) => route.id === activeRoute)?.component ?? routes[0].component,
    [activeRoute],
  )

  const handleRouteChange = useCallback((routeId: RouteId) => {
    setActiveRoute(routeId)
    window.location.hash = `/${routeId}`
  }, [])

  return (
    <AppShell activeRoute={activeRoute} onRouteChange={handleRouteChange}>
      <RouteErrorBoundary key={activeRoute}>
        <Suspense fallback={<RouteLoadingFallback />}>
          <ActiveView />
        </Suspense>
      </RouteErrorBoundary>
    </AppShell>
  )
}

function RouteLoadingFallback() {
  return (
    <div className="space-y-3">
      <div className="rounded-md border border-slate-200 bg-white px-3 py-3">
        <div className="h-3 w-24 animate-pulse rounded bg-slate-100" />
        <div className="mt-3 h-4 w-full max-w-xs animate-pulse rounded bg-slate-100" />
        <div className="mt-2 h-3 w-full max-w-lg animate-pulse rounded bg-slate-100" />
      </div>
      <div className="grid grid-cols-1 gap-3 xl:grid-cols-[minmax(0,1fr)_380px]">
        <div className="space-y-3 rounded-md border border-slate-200 bg-white p-3">
          <div className="flex items-center justify-between gap-3">
            <div>
              <div className="h-3 w-24 animate-pulse rounded bg-slate-100" />
              <div className="mt-2 h-3 w-40 animate-pulse rounded bg-slate-100" />
            </div>
            <div className="h-8 w-24 animate-pulse rounded-md bg-slate-100" />
          </div>
          <div className="h-32 animate-pulse rounded-md bg-slate-100 sm:h-52" />
          <div className="flex gap-2 overflow-hidden">
            <div className="h-7 w-48 shrink-0 animate-pulse rounded-md bg-slate-100" />
            <div className="h-7 w-44 shrink-0 animate-pulse rounded-md bg-slate-100" />
            <div className="h-7 w-36 shrink-0 animate-pulse rounded-md bg-slate-100" />
          </div>
        </div>
        <div className="space-y-3 rounded-md border border-slate-200 bg-white p-3">
          <div className="h-3 w-28 animate-pulse rounded bg-slate-100" />
          <div className="h-8 animate-pulse rounded-md bg-slate-100" />
          <div className="grid grid-cols-2 gap-2">
            <div className="h-10 animate-pulse rounded-md bg-slate-100" />
            <div className="h-10 animate-pulse rounded-md bg-slate-100" />
          </div>
          <div className="h-8 animate-pulse rounded-md bg-slate-100" />
        </div>
      </div>
    </div>
  )
}

export default function App() {
  return (
    <AppProviders>
      <RootRouter />
    </AppProviders>
  )
}

function RootRouter() {
  const [path, setPath] = useState(() => normalizedPath())

  useEffect(() => {
    const handleNavigation = () => setPath(normalizedPath())
    window.addEventListener('popstate', handleNavigation)
    return () => window.removeEventListener('popstate', handleNavigation)
  }, [])

  if (path === '/') {
    return <ProductShell />
  }
  if (
    path === '/privacy' ||
    path === '/license' ||
    path === '/support' ||
    path === '/changelog' ||
    path === '/operations'
  ) {
    return <ProductShell page={path.slice(1) as ProductPage} />
  }
  if (path === '/setup') {
    return <AuthPage mode="setup" />
  }
  if (path === '/login') {
    return <AuthPage mode="login" />
  }

  return (
    <AuthGate>
      <StudioApp />
    </AuthGate>
  )
}

function normalizedPath() {
  const path = window.location.pathname.replace(/\/+$/, '')
  return path || '/'
}
