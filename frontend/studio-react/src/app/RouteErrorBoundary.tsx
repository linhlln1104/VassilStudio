import { Component, type ReactNode } from 'react'

import { Button } from '@/components/ui/button'

export class RouteErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false }

  static getDerivedStateFromError() { return { failed: true } }

  render() {
    if (this.state.failed) {
      return (
        <section className="rounded-md border border-red-200 bg-red-50 p-4" role="alert">
          <h2 className="text-sm font-semibold text-red-950">This view could not be opened</h2>
          <p className="mt-2 text-sm text-red-800">Your saved jobs and voice profiles are still available. Open another view or reload Studio to try again.</p>
          <Button className="mt-3" variant="secondary" onClick={() => window.location.reload()}>Reload Studio</Button>
        </section>
      )
    }
    return this.props.children
  }
}
