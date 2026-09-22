import { useState, type ReactNode } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import { motion } from 'framer-motion'
import { useMutation, useQuery } from '@tanstack/react-query'
import {
  Cpu,
  Loader2,
  LogOut,
  Menu,
  X,
} from 'lucide-react'

import { Button } from '@/components/ui/button'
import { useToast } from '@/components/ui/use-toast'
import { api } from '@/lib/api'
import { BRAND_LOGO_SRC, BRAND_NAME } from '@/lib/brand'
import { cn } from '@/lib/utils'
import { routes, type RouteId, type StudioRoute } from '@/app/routes'

type AppShellProps = {
  activeRoute: RouteId
  onRouteChange: (routeId: RouteId) => void
  children: ReactNode
}

const sections: StudioRoute['section'][] = ['Create', 'Manage', 'System']

export function AppShell({ activeRoute, onRouteChange, children }: AppShellProps) {
  const [mobileNavOpen, setMobileNavOpen] = useState(false)
  const activeRouteData = routes.find((route) => route.id === activeRoute) ?? routes[0]
  const ActiveRouteIcon = activeRouteData.icon

  const handleRouteSelect = (routeId: RouteId) => {
    onRouteChange(routeId)
    setMobileNavOpen(false)
  }

  return (
    <Dialog.Root open={mobileNavOpen} onOpenChange={setMobileNavOpen}>
    <div className="min-h-screen bg-studio-canvas text-studio-ink">
      <div className="flex min-h-screen">
        <aside className="hidden w-[236px] shrink-0 border-r border-studio-border bg-white px-3 py-4 lg:block">
          <NavigationRail
            activeRoute={activeRoute}
            onRouteChange={handleRouteSelect}
          />
        </aside>

        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-40 bg-neutral-950/35" />
          <Dialog.Content className="fixed inset-y-0 left-0 z-50 w-[min(82vw,296px)] border-r border-studio-border bg-white px-3 py-4 shadow-xl outline-none">
            <Dialog.Title className="sr-only">Studio navigation</Dialog.Title>
            <Dialog.Description className="sr-only">Choose a Studio view.</Dialog.Description>
            <Dialog.Close asChild>
              <Button
                className="absolute right-3 top-3"
                size="icon"
                variant="ghost"
                aria-label="Close navigation"
              >
                <X className="size-4" />
              </Button>
            </Dialog.Close>
            <NavigationRail activeRoute={activeRoute} onRouteChange={handleRouteSelect} />
          </Dialog.Content>
        </Dialog.Portal>

        <main className="flex min-w-0 flex-1 flex-col">
          <header className="sticky top-0 z-30 border-b border-studio-border bg-white/95 backdrop-blur-sm">
            <div className="flex min-h-14 items-center gap-2 px-3 sm:px-5 lg:px-6">
              <Dialog.Trigger asChild>
                <Button className="lg:hidden" size="icon" variant="ghost" aria-label="Open navigation">
                  <Menu className="size-5" />
                </Button>
              </Dialog.Trigger>

              <div className="min-w-0 flex-1">
                <div className="flex min-w-0 items-center gap-2.5 text-sm font-semibold text-studio-ink">
                  <span className="grid size-7 shrink-0 place-items-center rounded-md border border-studio-border bg-studio-paper text-neutral-600">
                    <ActiveRouteIcon className="size-4" />
                  </span>
                  <h1 className="truncate">{activeRouteData.label}</h1>
                </div>
              </div>

              <RuntimeStatus onOpen={() => handleRouteSelect('settings')} />
              <SessionControl />
            </div>
          </header>

          <div className="flex-1 px-3 py-4 sm:px-5 lg:px-6 lg:py-5">
            <motion.div
              key={activeRoute}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.18, ease: 'easeOut' }}
              className="mx-auto w-full max-w-[1440px]"
            >
              {children}
            </motion.div>
          </div>
        </main>
      </div>
    </div>
    </Dialog.Root>
  )
}

function RuntimeStatus({ onOpen }: { onOpen: () => void }) {
  const statusQuery = useQuery({
    queryKey: ['model-status'],
    queryFn: api.modelStatus,
    staleTime: 30_000,
    refetchInterval: 30_000,
    retry: 1,
  })

  const loaded = Boolean(statusQuery.data?.runtime.asr_loaded || statusQuery.data?.runtime.tts_loaded)
  const state = statusQuery.isError
    ? { label: 'Runtime unavailable', dot: 'bg-red-500', text: 'text-red-700' }
    : statusQuery.data?.ready
      ? { label: 'Models ready', dot: 'bg-emerald-500', text: 'text-neutral-600' }
      : loaded
        ? { label: 'Partially ready', dot: 'bg-amber-500', text: 'text-neutral-600' }
        : statusQuery.isPending
          ? { label: 'Checking models', dot: 'bg-neutral-300', text: 'text-neutral-500' }
          : { label: 'Models cold', dot: 'bg-amber-500', text: 'text-neutral-600' }

  return (
    <button
      type="button"
      className="flex h-8 items-center gap-2 rounded-md border border-studio-border bg-white px-2 text-xs font-medium transition-colors hover:bg-neutral-50 sm:px-2.5"
      title={state.label}
      aria-label={`${state.label}. Open Settings`}
      onClick={onOpen}
    >
      <Cpu className="size-3.5 text-neutral-500" />
      <span className={cn('size-1.5 rounded-full', state.dot)} />
      <span className={cn('hidden sm:inline', state.text)}>{state.label}</span>
    </button>
  )
}

function SessionControl() {
  const { toast } = useToast()
  const authQuery = useQuery({
    queryKey: ['auth-status'],
    queryFn: api.authStatus,
    staleTime: 10_000,
  })
  const logoutMutation = useMutation({
    mutationFn: api.authLogout,
    onSuccess: () => {
      window.location.assign('/login')
    },
    onError: (error) => {
      toast({
        title: 'Sign out failed',
        description: error instanceof Error ? error.message : 'Unable to end this session.',
        variant: 'danger',
      })
    },
  })

  if (!authQuery.data?.auth_required) {
    return null
  }

  return (
    <div className="flex min-w-0 items-center gap-2">
      <div className="hidden max-w-[180px] truncate text-xs font-medium text-neutral-500 md:block">
        {authQuery.data.user?.username ?? 'Signed in'}
      </div>
      <Button
        size="icon"
        variant="ghost"
        aria-label="Sign out"
        onClick={() => logoutMutation.mutate()}
        disabled={logoutMutation.isPending}
      >
        {logoutMutation.isPending ? <Loader2 className="size-4 animate-spin" /> : <LogOut className="size-4" />}
      </Button>
    </div>
  )
}

type NavigationRailProps = {
  activeRoute: RouteId
  onRouteChange: (routeId: RouteId) => void
}

function NavigationRail({
  activeRoute,
  onRouteChange,
}: NavigationRailProps) {
  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="mb-6 flex h-9 items-center gap-2.5 px-1 pr-9">
        <img
          className="h-8 w-auto max-w-[156px] shrink-0 object-contain"
          src={BRAND_LOGO_SRC}
          alt={BRAND_NAME}
        />
      </div>

      <nav className="flex-1 space-y-5 overflow-y-auto pr-1">
        {sections.map((section) => (
          <div key={section}>
            <div className="mb-1.5 px-2.5 text-[11px] font-semibold text-neutral-400">
              {section}
            </div>
            <div className="space-y-1">
              {routes
                .filter((route) => route.section === section)
                .map((route) => (
                  <NavItem
                    key={route.id}
                    active={activeRoute === route.id}
                    route={route}
                    onSelect={() => onRouteChange(route.id)}
                  />
                ))}
            </div>
          </div>
        ))}
      </nav>
    </div>
  )
}

function NavItem({
  route,
  active,
  onSelect,
}: {
  route: StudioRoute
  active: boolean
  onSelect: () => void
}) {
  const RouteIcon = route.icon

  return (
    <button
      type="button"
      onClick={onSelect}
      aria-current={active ? 'page' : undefined}
      className={cn(
        'flex h-9 w-full items-center gap-2.5 rounded-md px-2.5 text-left text-[13px] font-medium transition-colors',
        active
          ? 'bg-blue-50 text-blue-700'
          : 'text-neutral-600 hover:bg-neutral-100 hover:text-neutral-950',
      )}
    >
      <RouteIcon className={cn('size-4 shrink-0', active ? 'text-blue-600' : 'text-neutral-500')} />
      <span className="min-w-0 flex-1 truncate">{route.label}</span>
    </button>
  )
}
