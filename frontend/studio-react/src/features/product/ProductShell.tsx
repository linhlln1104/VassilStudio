import { ArrowRight, AudioLines, Captions, Database, ShieldCheck } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { BRAND_LOGO_SRC, BRAND_NAME } from '@/lib/brand'

type ProductShellProps = {
  page?: 'home' | 'privacy' | 'license' | 'support' | 'changelog' | 'operations'
}

export function ProductShell({ page = 'home' }: ProductShellProps) {
  if (page !== 'home') {
    return <InfoPage page={page} />
  }

  return (
    <div className="min-h-screen bg-white text-slate-950">
      <header className="sticky top-0 z-20 border-b border-slate-200 bg-white/95">
        <div className="mx-auto flex h-14 max-w-[1180px] items-center justify-between px-4 sm:px-6">
          <a className="inline-flex items-center" href="/">
            <img className="h-8 w-auto" src={BRAND_LOGO_SRC} alt={BRAND_NAME} />
          </a>
          <nav className="hidden items-center gap-5 text-xs font-medium text-slate-500 sm:flex">
            <a className="hover:text-slate-950" href="/operations">Docs</a>
            <a className="hover:text-slate-950" href="/changelog">Changelog</a>
            <a className="hover:text-slate-950" href="/support">Support</a>
            <a className="hover:text-slate-950" href="/privacy">Privacy</a>
            <a className="hover:text-slate-950" href="/license">License</a>
          </nav>
          <Button asChild size="sm">
            <a href="/studio">
              Open Studio
              <ArrowRight className="size-3.5" />
            </a>
          </Button>
        </div>
      </header>

      <main>
        <section className="mx-auto grid min-h-[calc(100vh-56px)] max-w-[1180px] content-center gap-8 px-4 py-12 sm:px-6 lg:grid-cols-[minmax(0,1fr)_440px]">
          <div className="max-w-2xl">
            <div className="inline-flex h-8 items-center gap-2 rounded-md border border-slate-200 px-2.5 text-xs font-medium text-slate-600">
              <ShieldCheck className="size-3.5 text-blue-600" />
              Local-first voice studio
            </div>
            <h1 className="mt-6 text-5xl font-semibold tracking-normal text-slate-950 sm:text-6xl">
              VassilStudio
            </h1>
            <p className="mt-5 max-w-xl text-base leading-7 text-slate-600">
              A focused workspace for ZipFormer ASR, ZipVoice TTS, reusable voice profiles, and local diagnostics.
            </p>
            <div className="mt-7 flex flex-wrap gap-2">
              <Button asChild>
                <a href="/studio">
                  Open Studio
                  <ArrowRight className="size-3.5" />
                </a>
              </Button>
              <Button asChild variant="secondary">
                <a href="/operations">Read operations guide</a>
              </Button>
            </div>
          </div>

          <ProductPreview />
        </section>

        <section className="border-t border-slate-200">
          <div className="mx-auto grid max-w-[1180px] gap-0 px-4 py-10 sm:px-6 md:grid-cols-3">
            {[
              ['Voice profiles', 'Import reference audio and keep language metadata attached.'],
              ['Render queue', 'Preview and production jobs stay visible until cleanup.'],
              ['Diagnostics', 'Readiness, warmup, storage, and logs stay close to the work.'],
            ].map(([title, copy]) => (
              <div className="border-b border-slate-200 py-4 md:border-b-0 md:border-r md:px-5 md:last:border-r-0" key={title}>
                <div className="text-sm font-semibold text-slate-950">{title}</div>
                <p className="mt-1 text-xs leading-5 text-slate-600">{copy}</p>
              </div>
            ))}
          </div>
        </section>
      </main>
    </div>
  )
}

function ProductPreview() {
  return (
    <div className="rounded-md border border-slate-200 bg-white p-3 shadow-sm">
      <div className="flex items-center justify-between border-b border-slate-200 pb-2">
        <div className="text-xs font-semibold text-slate-950">Workspace readiness</div>
        <div className="rounded-md bg-blue-50 px-2 py-1 text-xs font-medium text-blue-700">Ready</div>
      </div>
      <div className="mt-3 grid gap-2">
        <PreviewRow icon={AudioLines} title="Generate" value="2 voice profiles" />
        <PreviewRow icon={Captions} title="Transcribe" value="Vietnamese + English" />
        <PreviewRow icon={Database} title="Jobs" value="Queue tracked locally" />
      </div>
      <div className="mt-4 h-24 rounded-md border border-slate-200 bg-slate-50 p-3">
        <div className="h-2 w-24 rounded bg-slate-200" />
        <div className="mt-3 flex items-end gap-1">
          {[32, 54, 42, 68, 36, 58, 44, 62, 28, 48, 72, 38].map((height, index) => (
            <div
              className="w-full rounded-t bg-blue-500"
              style={{ height }}
              key={`${height}-${index}`}
            />
          ))}
        </div>
      </div>
    </div>
  )
}

function PreviewRow({
  icon: Icon,
  title,
  value,
}: {
  icon: typeof AudioLines
  title: string
  value: string
}) {
  return (
    <div className="flex min-h-10 items-center gap-2 rounded-md border border-slate-200 px-2.5">
      <Icon className="size-4 text-slate-500" />
      <div className="min-w-0 flex-1">
        <div className="truncate text-xs font-semibold text-slate-950">{title}</div>
        <div className="truncate text-xs text-slate-500">{value}</div>
      </div>
    </div>
  )
}

function InfoPage({ page }: { page: 'privacy' | 'license' | 'support' | 'changelog' | 'operations' }) {
  const content = {
    privacy: ['Privacy', 'Audio, transcripts, voice profiles, jobs, and diagnostics stay in the local workspace by default. External telemetry is off by default.'],
    license: ['License', 'App, model, and third-party license notes belong here before a packaged release.'],
    support: ['Support', 'Run diagnostics, check model readiness, review logs, then attach a redacted support bundle when reporting issues.'],
    changelog: ['Changelog', 'Production hardening, local auth, onboarding, diagnostics, storage retention, and benchmark tooling are tracked in the repository changelog.'],
    operations: ['Operations guide', 'Install, model layout, config, local auth, smoke tests, Docker, backup, and troubleshooting live in docs/operations.md.'],
  }[page]

  return (
    <div className="min-h-screen bg-white text-slate-950">
      <div className="mx-auto flex min-h-screen max-w-3xl flex-col px-4 py-4 sm:px-6">
        <header className="flex h-12 items-center justify-between">
          <a href="/">
            <img className="h-8 w-auto" src={BRAND_LOGO_SRC} alt={BRAND_NAME} />
          </a>
          <Button asChild size="sm" variant="secondary">
            <a href="/studio">Open Studio</a>
          </Button>
        </header>
        <main className="flex flex-1 flex-col justify-center py-12">
          <h1 className="text-4xl font-semibold tracking-normal">{content[0]}</h1>
          <p className="mt-4 text-sm leading-6 text-slate-600">{content[1]}</p>
        </main>
      </div>
    </div>
  )
}
