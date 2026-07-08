import { useEffect, useState, type FormEvent } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { ArrowRight, LockKeyhole, UserPlus } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { api } from '@/lib/api'
import { BRAND_LOGO_SRC, BRAND_NAME } from '@/lib/brand'

type AuthPageProps = {
  mode: 'setup' | 'login'
}

export function AuthPage({ mode }: AuthPageProps) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const statusQuery = useQuery({
    queryKey: ['auth-status'],
    queryFn: api.authStatus,
  })
  const mutation = useMutation({
    mutationFn: mode === 'setup' ? api.authSetup : api.authLogin,
    onSuccess: () => {
      window.location.assign('/studio')
    },
  })

  const status = statusQuery.data

  useEffect(() => {
    if (!status) {
      return
    }
    if (!status.auth_required) {
      window.location.assign('/studio')
      return
    }
    if (mode === 'setup' && !status.setup_required) {
      window.location.assign(status.authenticated ? '/studio' : '/login')
      return
    }
    if (mode === 'login' && status.setup_required) {
      window.location.assign('/setup')
      return
    }
    if (mode === 'login' && status.authenticated) {
      window.location.assign('/studio')
    }
  }, [mode, status])

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    mutation.mutate({ username, password })
  }

  const isSetup = mode === 'setup'
  const Icon = isSetup ? UserPlus : LockKeyhole

  return (
    <div className="min-h-screen bg-white text-slate-950">
      <div className="mx-auto flex min-h-screen w-full max-w-[1120px] flex-col px-4 py-4 sm:px-6">
        <header className="flex h-12 items-center justify-between">
          <a className="inline-flex items-center" href="/">
            <img className="h-8 w-auto" src={BRAND_LOGO_SRC} alt={BRAND_NAME} />
          </a>
          <a className="text-xs font-medium text-slate-500 hover:text-slate-950" href="/">
            Product
          </a>
        </header>

        <main className="grid flex-1 items-center gap-8 py-8 lg:grid-cols-[minmax(0,1fr)_380px]">
          <section className="max-w-2xl">
            <div className="inline-flex h-8 items-center gap-2 rounded-md border border-slate-200 px-2.5 text-xs font-medium text-slate-600">
              <Icon className="size-3.5 text-blue-600" />
              {isSetup ? 'First-run workspace' : 'Workspace session'}
            </div>
            <h1 className="mt-5 text-4xl font-semibold tracking-normal text-slate-950 sm:text-5xl">
              VassilStudio
            </h1>
            <p className="mt-4 max-w-xl text-sm leading-6 text-slate-600">
              Local voice profiles, render queue, ASR transcripts, and diagnostics stay inside this workspace.
            </p>
          </section>

          <form
            className="rounded-md border border-slate-200 bg-white p-4 shadow-sm"
            onSubmit={handleSubmit}
          >
            <div className="text-sm font-semibold text-slate-950">
              {isSetup ? 'Create owner account' : 'Sign in'}
            </div>
            <div className="mt-1 text-xs leading-5 text-slate-500">
              {isSetup ? 'Used only on this local workspace.' : 'Continue to Studio.'}
            </div>

            <label className="mt-5 block text-xs font-medium text-slate-700">
              Username
              <input
                className="mt-1 h-9 w-full rounded-md border border-slate-200 bg-white px-2.5 text-sm text-slate-950 outline-none transition focus:border-blue-400 focus:ring-2 focus:ring-blue-100"
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                autoComplete={isSetup ? 'username' : 'username'}
                required
                minLength={3}
                maxLength={80}
              />
            </label>

            <label className="mt-3 block text-xs font-medium text-slate-700">
              Password
              <input
                className="mt-1 h-9 w-full rounded-md border border-slate-200 bg-white px-2.5 text-sm text-slate-950 outline-none transition focus:border-blue-400 focus:ring-2 focus:ring-blue-100"
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                autoComplete={isSetup ? 'new-password' : 'current-password'}
                required
                minLength={isSetup ? 8 : 1}
                maxLength={512}
              />
            </label>

            {mutation.isError ? (
              <div className="mt-3 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
                {mutation.error.message}
              </div>
            ) : null}

            <Button className="mt-4 w-full" type="submit" disabled={mutation.isPending}>
              {mutation.isPending ? 'Working' : isSetup ? 'Create workspace' : 'Open Studio'}
              <ArrowRight className="size-3.5" />
            </Button>
          </form>
        </main>
      </div>
    </div>
  )
}
