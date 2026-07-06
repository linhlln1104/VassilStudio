import { useState, type ReactNode } from 'react'
import { motion } from 'framer-motion'
import {
  Menu,
  X,
} from 'lucide-react'

import { Button } from '@/components/ui/button'
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
    <div className="min-h-screen bg-white text-slate-950">
      <div className="flex min-h-screen">
        <aside className="hidden w-60 shrink-0 border-r border-slate-200 bg-white px-2.5 py-3 lg:block">
          <NavigationRail
            activeRoute={activeRoute}
            onRouteChange={handleRouteSelect}
          />
        </aside>

        {mobileNavOpen ? (
          <div className="fixed inset-0 z-40 lg:hidden">
            <button
              className="absolute inset-0 bg-slate-950/30"
              type="button"
              aria-label="Close navigation"
              onClick={() => setMobileNavOpen(false)}
            />
            <motion.aside
              initial={{ x: -320, opacity: 0.96 }}
              animate={{ x: 0, opacity: 1 }}
              exit={{ x: -320, opacity: 0.96 }}
              transition={{ duration: 0.2, ease: 'easeOut' }}
              className="relative h-full w-[min(84vw,288px)] border-r border-slate-200 bg-white px-3 py-4 shadow-2xl"
            >
              <Button
                className="absolute right-3 top-3"
                size="icon"
                variant="ghost"
                onClick={() => setMobileNavOpen(false)}
                aria-label="Close navigation"
              >
                <X className="size-4" />
              </Button>
              <NavigationRail
                activeRoute={activeRoute}
                onRouteChange={handleRouteSelect}
              />
            </motion.aside>
          </div>
        ) : null}

        <main className="flex min-w-0 flex-1 flex-col">
          <header className="sticky top-0 z-30 border-b border-slate-200 bg-white relative">
            <div className="flex min-h-11 items-center gap-2 px-3 sm:px-4">
              <Button
                className="lg:hidden"
                size="icon"
                variant="ghost"
                onClick={() => setMobileNavOpen(true)}
                aria-label="Open navigation"
              >
                <Menu className="size-5" />
              </Button>

              <div className="min-w-0 flex-1">
                <div className="flex min-w-0 items-center gap-2 text-sm font-semibold text-slate-950">
                  <ActiveRouteIcon className="size-4 shrink-0 text-slate-500" />
                  <span className="truncate">{activeRouteData.label}</span>
                </div>
              </div>
            </div>
            <div className="absolute inset-x-0 bottom-0 h-px bg-gradient-to-r from-transparent via-blue-500/25 to-transparent" />
          </header>

          <div className="flex-1 px-3 py-3 sm:px-4 lg:px-5">
            <motion.div
              key={activeRoute}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.22, ease: 'easeOut' }}
              className="mx-auto w-full max-w-[1360px]"
            >
              {children}
            </motion.div>
          </div>
        </main>
      </div>
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
      <div className="mb-5 flex items-center gap-2.5 pr-8">
        <img
          className="h-8 w-auto max-w-[150px] shrink-0 object-contain"
          src={BRAND_LOGO_SRC}
          alt={BRAND_NAME}
        />
      </div>

      <nav className="flex-1 space-y-4 overflow-y-auto pr-1">
        {sections.map((section) => (
          <div key={section}>
            <div className="mb-1.5 px-2 text-xs font-semibold text-slate-400">
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
      className={cn(
        'flex min-h-7 w-full items-center gap-2 rounded-md px-2 py-1 text-left text-xs font-medium transition-colors',
        active
          ? 'bg-gradient-to-r from-sky-50 via-white to-fuchsia-50 text-blue-700 ring-1 ring-inset ring-sky-100'
          : 'text-slate-600 hover:bg-slate-50 hover:text-slate-950',
      )}
    >
      <RouteIcon className="size-3.5 shrink-0" />
      <span className="min-w-0 flex-1 truncate">{route.label}</span>
    </button>
  )
}
