import { useEffect, useId, useState, type FormEvent } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import {
  AlertTriangle,
  ArrowRight,
  Eye,
  EyeOff,
  Loader2,
  LockKeyhole,
  RefreshCw,
  UserPlus,
} from 'lucide-react'

import { Button } from '@/components/ui/button'
import { api } from '@/lib/api'
import { authPageUrl, authReturnTo } from '@/lib/auth-navigation'
import { BRAND_LOGO_SRC, BRAND_NAME } from '@/lib/brand'

type AuthPageProps = {
  mode: 'setup' | 'login'
}

export function AuthPage({ mode }: AuthPageProps) {
  const returnTo = authReturnTo()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const statusQuery = useQuery({
    queryKey: ['auth-status'],
    queryFn: api.authStatus,
  })
  const mutation = useMutation({
    mutationFn: mode === 'setup' ? api.authSetup : api.authLogin,
    onSuccess: () => {
      window.location.assign(returnTo)
    },
  })

  const status = statusQuery.data

  useEffect(() => {
    if (!status) {
      return
    }
    if (!status.auth_required) {
      window.location.assign(returnTo)
      return
    }
    if (mode === 'setup' && !status.setup_required) {
      window.location.assign(status.authenticated ? returnTo : authPageUrl('login', returnTo))
      return
    }
    if (mode === 'login' && status.setup_required) {
      window.location.assign(authPageUrl('setup', returnTo))
      return
    }
    if (mode === 'login' && status.authenticated) {
      window.location.assign(returnTo)
    }
  }, [mode, returnTo, status])

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (statusQuery.isPending || statusQuery.isError || (mode === 'setup' && password !== confirmPassword)) {
      return
    }
    mutation.mutate({ username: username.trim(), password })
  }

  const isSetup = mode === 'setup'
  const Icon = isSetup ? UserPlus : LockKeyhole
  const passwordMismatch = isSetup && confirmPassword.length > 0 && password !== confirmPassword
  const canSubmit =
    username.trim().length >= 3 &&
    password.length >= (isSetup ? 8 : 1) &&
    (!isSetup || password === confirmPassword) &&
    !statusQuery.isPending &&
    !statusQuery.isError &&
    !mutation.isPending

  return (
    <div className="min-h-screen bg-white text-slate-950">
      <div className="mx-auto flex min-h-screen w-full max-w-[1120px] flex-col px-4 py-4 sm:px-6">
        <header className="flex h-12 items-center justify-between">
          <a className="inline-flex items-center" href="/">
            <img className="h-8 w-auto" src={BRAND_LOGO_SRC} alt={BRAND_NAME} />
          </a>
          <a className="text-xs font-medium text-slate-500 hover:text-slate-950" href="/">
            Home
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
            aria-busy={mutation.isPending}
          >
            <div className="text-sm font-semibold text-slate-950">
              {isSetup ? 'Create owner account' : 'Sign in'}
            </div>
            <div className="mt-1 text-xs leading-5 text-slate-500">
               {isSetup ? 'Used only on this local workspace.' : 'Continue to Studio.'}
             </div>

            {statusQuery.isPending ? (
              <div className="mt-4 flex items-center gap-2 rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-xs font-medium text-slate-600">
                <Loader2 className="size-4 animate-spin" />
                Checking workspace
              </div>
            ) : null}
            {statusQuery.isError ? (
              <div className="mt-4 rounded-md border border-red-200 bg-red-50 p-3" role="alert">
                <div className="flex items-start gap-2 text-xs font-semibold text-red-800">
                  <AlertTriangle className="mt-0.5 size-4 shrink-0" />
                  <span>Unable to reach the local authentication service.</span>
                </div>
                <Button
                  className="mt-3"
                  size="sm"
                  variant="secondary"
                  type="button"
                  onClick={() => { void statusQuery.refetch() }}
                >
                  <RefreshCw className="size-4" />
                  Retry
                </Button>
              </div>
            ) : null}

            <label className="mt-5 block text-xs font-medium text-slate-700">
              Username
              <input
                className="mt-1 h-9 w-full rounded-md border border-slate-200 bg-white px-2.5 text-sm text-slate-950 outline-none transition focus:border-blue-400 focus:ring-2 focus:ring-blue-100"
                value={username}
                onChange={(event) => {
                  setUsername(event.target.value)
                  mutation.reset()
                }}
                autoComplete="username"
                autoFocus
                required
                minLength={3}
                maxLength={80}
              />
            </label>

            <AuthPasswordField
              className="mt-3"
              label="Password"
              value={password}
              visible={showPassword}
              showToggle
              autoComplete={isSetup ? 'new-password' : 'current-password'}
              minLength={isSetup ? 8 : 1}
              onToggle={() => setShowPassword((current) => !current)}
              onChange={(value) => {
                setPassword(value)
                mutation.reset()
              }}
            />

            {isSetup ? (
              <AuthPasswordField
                className="mt-3"
                label="Confirm password"
                value={confirmPassword}
                visible={showPassword}
                autoComplete="new-password"
                minLength={8}
                invalid={passwordMismatch}
                onChange={(value) => {
                  setConfirmPassword(value)
                  mutation.reset()
                }}
              />
            ) : null}

            {isSetup ? (
              <div className={passwordMismatch ? 'mt-2 text-xs font-medium text-red-700' : 'mt-2 text-xs text-slate-500'}>
                {passwordMismatch ? 'Passwords do not match.' : 'Use at least 8 characters.'}
              </div>
            ) : null}

            {mutation.isError ? (
              <div className="mt-3 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
                {mutation.error instanceof Error ? mutation.error.message : 'Authentication failed.'}
              </div>
            ) : null}

            <Button className="mt-4 w-full" type="submit" disabled={!canSubmit}>
              {mutation.isPending ? <Loader2 className="size-4 animate-spin" /> : null}
              {mutation.isPending ? 'Working' : isSetup ? 'Create workspace' : 'Open Studio'}
              {!mutation.isPending ? <ArrowRight className="size-3.5" /> : null}
            </Button>
          </form>
        </main>
      </div>
    </div>
  )
}

function AuthPasswordField({
  label,
  value,
  visible,
  autoComplete,
  minLength,
  invalid = false,
  showToggle = false,
  className = '',
  onChange,
  onToggle,
}: {
  label: string
  value: string
  visible: boolean
  autoComplete: string
  minLength: number
  invalid?: boolean
  showToggle?: boolean
  className?: string
  onChange: (value: string) => void
  onToggle?: () => void
}) {
  const inputId = useId()
  return (
    <div className={`block text-xs font-medium text-slate-700 ${className}`}>
      <label htmlFor={inputId}>{label}</label>
      <div className="mt-1 flex rounded-md border border-slate-200 bg-white focus-within:border-blue-400 focus-within:ring-2 focus-within:ring-blue-100 aria-invalid:border-red-400 aria-invalid:ring-red-100" aria-invalid={invalid}>
        <input
          id={inputId}
          className="h-9 min-w-0 flex-1 border-0 bg-transparent px-2.5 text-sm text-slate-950 outline-none"
          type={visible ? 'text' : 'password'}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          autoComplete={autoComplete}
          required
          minLength={minLength}
          maxLength={512}
          aria-invalid={invalid}
        />
        {showToggle ? (
          <button
            className="grid size-9 shrink-0 place-items-center text-slate-500 hover:text-slate-950"
            type="button"
            aria-label={visible ? 'Hide password' : 'Show password'}
            title={visible ? 'Hide password' : 'Show password'}
            onClick={onToggle}
          >
            {visible ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
          </button>
        ) : null}
      </div>
    </div>
  )
}
