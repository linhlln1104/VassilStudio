import {
  ArrowRight,
  AudioLines,
  Captions,
  Cpu,
  Database,
  HardDrive,
  History,
  LockKeyhole,
  Mic,
  Settings,
  ShieldCheck,
  UsersRound,
} from 'lucide-react'

import { Button } from '@/components/ui/button'
import { BRAND_LOGO_SRC, BRAND_NAME } from '@/lib/brand'

type InfoPageId = 'privacy' | 'license' | 'support' | 'changelog' | 'operations'

type ProductShellProps = {
  page?: 'home' | InfoPageId
}

type InfoPageContent = {
  title: string
  summary: string
  rows: Array<{ label: string; value: string }>
  primaryAction?: { label: string; href: string }
  secondaryAction?: { label: string; href: string }
}

const publicLinks: Array<{ label: string; href: string; page: InfoPageId }> = [
  { label: 'Operations', href: '/operations', page: 'operations' },
  { label: 'Changelog', href: '/changelog', page: 'changelog' },
  { label: 'Support', href: '/support', page: 'support' },
  { label: 'Privacy', href: '/privacy', page: 'privacy' },
  { label: 'License', href: '/license', page: 'license' },
]

const workflowItems = [
  {
    icon: AudioLines,
    title: 'Generate',
    copy: 'Render Vietnamese or English speech from a saved voice profile.',
  },
  {
    icon: Captions,
    title: 'Transcribe',
    copy: 'Queue local audio for ZipFormer recognition and reuse the result.',
  },
  {
    icon: Mic,
    title: 'Realtime',
    copy: 'Stream microphone audio into a live local transcript session.',
  },
  {
    icon: UsersRound,
    title: 'Voices',
    copy: 'Create and maintain reusable reference voice profiles.',
  },
  {
    icon: History,
    title: 'Jobs',
    copy: 'Review queue state, outputs, failures, retries, and cleanup.',
  },
  {
    icon: Settings,
    title: 'Settings',
    copy: 'Inspect models, storage, authentication, and diagnostics.',
  },
]

const infoPages: Record<InfoPageId, InfoPageContent> = {
  privacy: {
    title: 'Privacy',
    summary: 'VassilStudio is designed for local voice work where data stays in the workspace.',
    rows: [
      {
        label: 'Local data',
        value: 'Audio, transcripts, voice profiles, outputs, jobs, and auth data stay under configured local paths.',
      },
      {
        label: 'Telemetry',
        value: 'External telemetry is disabled by default. Operators control any future integrations through configuration.',
      },
      {
        label: 'Diagnostics',
        value: 'Support bundles redact API keys, session secrets, cookies, transcripts, and private audio.',
      },
    ],
    primaryAction: { label: 'Open Studio', href: '/studio' },
    secondaryAction: { label: 'Support', href: '/support' },
  },
  license: {
    title: 'License',
    summary: 'VassilStudio is distributed source-first under GPL-3.0-or-later.',
    rows: [
      {
        label: 'Application',
        value: 'Application source is GPL-3.0-or-later. The repository LICENSE contains the full terms.',
      },
      {
        label: 'Models',
        value: 'Models and datasets are installed separately and remain subject to their own terms.',
      },
      {
        label: 'Dependencies',
        value: 'Runtime and frontend dependencies retain their upstream licenses and notices.',
      },
    ],
    primaryAction: { label: 'Operations guide', href: '/operations' },
  },
  support: {
    title: 'Support',
    summary: 'Start with readiness, logs, and a redacted diagnostics bundle before reporting an issue.',
    rows: [
      {
        label: 'Readiness',
        value: 'Check Settings, /model-status, /health, and scripts/doctor.ps1 for missing runtime assets.',
      },
      {
        label: 'Bundle',
        value: 'Download /diagnostics/bundle after reproducing the issue. It is designed for safe sharing.',
      },
      {
        label: 'Quality gate',
        value: 'Run scripts/check.ps1 before reporting regressions from local source changes.',
      },
    ],
    primaryAction: { label: 'Operations guide', href: '/operations' },
    secondaryAction: { label: 'Open Studio', href: '/studio' },
  },
  changelog: {
    title: 'Changelog',
    summary: 'Product and production-hardening work is recorded in commits and CHANGELOG.md.',
    rows: [
      {
        label: 'Current release',
        value: '0.1.0-local-product covers complete voice workflows, local auth, diagnostics, and retention.',
      },
      {
        label: 'Verification',
        value: 'Each production phase records scripts/check.ps1 results before commit and push.',
      },
      {
        label: 'Contracts',
        value: 'OpenAPI contracts are regenerated as part of the default quality gate.',
      },
    ],
    primaryAction: { label: 'Open Studio', href: '/studio' },
  },
  operations: {
    title: 'Operations guide',
    summary: 'The runbook in docs/operations.md covers local installation through release checks.',
    rows: [
      {
        label: 'Setup',
        value: 'Install, model layout, configuration, local auth, smoke scripts, and Docker are documented.',
      },
      {
        label: 'Maintenance',
        value: 'Storage cleanup, diagnostics bundles, backup, restore, and Windows path notes are included.',
      },
      {
        label: 'Release',
        value: 'Use the runbook checklist with CHANGELOG.md and scripts/check.ps1 before distribution.',
      },
    ],
    primaryAction: { label: 'Open Studio', href: '/studio' },
    secondaryAction: { label: 'Support', href: '/support' },
  },
}

export function ProductShell({ page = 'home' }: ProductShellProps) {
  if (page !== 'home') {
    return <InfoPage page={page} />
  }

  return (
    <div className="min-h-screen bg-white text-slate-950">
      <PublicHeader />
      <main>
        <section className="relative h-[calc(100svh-112px)] min-h-[480px] max-h-[760px] overflow-hidden border-b border-slate-200">
          <img
            className="absolute inset-0 size-full object-cover object-top"
            src="/studio/brand/vassil-studio-realtime.png"
            alt="VassilStudio realtime transcription workspace"
          />
          <div className="absolute inset-0 bg-white/70" aria-hidden="true" />
          <div className="relative mx-auto flex h-full max-w-[1180px] items-end px-4 pb-10 sm:px-6 sm:pb-14">
            <div className="max-w-2xl">
              <div className="flex items-center gap-2 text-xs font-semibold text-blue-700">
                <ShieldCheck className="size-4" />
                Local-first voice studio
              </div>
              <h1 className="mt-4 text-5xl font-semibold tracking-normal text-slate-950 sm:text-6xl">
                VassilStudio
              </h1>
              <p className="mt-4 max-w-xl text-base leading-7 text-slate-700">
                ZipFormer transcription, ZipVoice rendering, reusable voice profiles, and runtime diagnostics in one local workspace.
              </p>
              <div className="mt-6 flex flex-wrap gap-2">
                <Button asChild>
                  <a href="/studio">
                    Open Studio
                    <ArrowRight className="size-4" />
                  </a>
                </Button>
                <Button asChild variant="secondary">
                  <a href="/operations">Operations guide</a>
                </Button>
              </div>
              <div className="mt-6 flex flex-wrap gap-x-5 gap-y-2 text-xs font-medium text-slate-700">
                <span>Vietnamese + English</span>
                <span>CPU runtime</span>
                <span>Local queue and storage</span>
              </div>
            </div>
          </div>
        </section>

        <section className="border-b border-slate-200 bg-white" aria-label="Product foundation">
          <div className="mx-auto grid min-h-24 max-w-[1180px] grid-cols-1 px-4 sm:grid-cols-3 sm:px-6">
            <FoundationItem icon={HardDrive} title="Local data" copy="Audio and outputs stay in configured workspace paths." />
            <FoundationItem icon={Cpu} title="Model aware" copy="Readiness, cold starts, and languages stay visible." />
            <FoundationItem icon={LockKeyhole} title="Operator controlled" copy="Local auth, API keys, diagnostics, and cleanup are explicit." />
          </div>
        </section>

        <section className="mx-auto max-w-[1180px] px-4 py-14 sm:px-6 sm:py-16">
          <div className="max-w-2xl">
            <div className="text-xs font-semibold text-blue-700">Studio workflows</div>
            <h2 className="mt-2 text-2xl font-semibold tracking-normal text-slate-950">From reference audio to finished output</h2>
            <p className="mt-3 text-sm leading-6 text-slate-600">
              Each workspace view handles one clear job and shares the same local runtime, queue, and language state.
            </p>
          </div>
          <div className="mt-8 grid grid-cols-1 border-t border-slate-200 sm:grid-cols-2 lg:grid-cols-3">
            {workflowItems.map((item) => (
              <article className="border-b border-slate-200 py-5 sm:px-4 sm:odd:border-r lg:border-r lg:odd:border-r lg:[&:nth-child(3n)]:border-r-0" key={item.title}>
                <item.icon className="size-5 text-blue-700" />
                <h3 className="mt-3 text-sm font-semibold text-slate-950">{item.title}</h3>
                <p className="mt-1 max-w-sm text-xs leading-5 text-slate-600">{item.copy}</p>
              </article>
            ))}
          </div>
        </section>

        <section className="border-y border-slate-200 bg-slate-50">
          <div className="mx-auto flex max-w-[1180px] flex-col gap-4 px-4 py-10 sm:flex-row sm:items-center sm:justify-between sm:px-6">
            <div>
              <div className="text-sm font-semibold text-slate-950">Ready to work locally</div>
              <div className="mt-1 text-xs leading-5 text-slate-600">Open the studio or review model layout and runtime operations first.</div>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button asChild>
                <a href="/studio">Open Studio</a>
              </Button>
              <Button asChild variant="secondary">
                <a href="/operations">Review operations</a>
              </Button>
            </div>
          </div>
        </section>
      </main>
      <PublicFooter />
    </div>
  )
}

function PublicHeader() {
  return (
    <header className="sticky top-0 z-20 border-b border-slate-200 bg-white/95">
      <div className="mx-auto flex h-14 max-w-[1180px] items-center justify-between gap-4 px-4 sm:px-6">
        <a className="inline-flex min-w-0 items-center" href="/" aria-label="VassilStudio home">
          <img className="h-8 w-auto max-w-[150px]" src={BRAND_LOGO_SRC} alt={BRAND_NAME} />
        </a>
        <nav className="hidden items-center gap-5 text-xs font-medium text-slate-500 lg:flex" aria-label="Product navigation">
          {publicLinks.map((link) => (
            <a className="hover:text-slate-950" href={link.href} key={link.page}>{link.label}</a>
          ))}
        </nav>
        <Button asChild size="sm">
          <a href="/studio">
            Open Studio
            <ArrowRight className="size-3.5" />
          </a>
        </Button>
      </div>
    </header>
  )
}

function FoundationItem({
  icon: Icon,
  title,
  copy,
}: {
  icon: typeof Database
  title: string
  copy: string
}) {
  return (
    <div className="flex items-start gap-3 border-b border-slate-200 py-4 last:border-b-0 sm:border-b-0 sm:border-r sm:px-5 sm:first:pl-0 sm:last:border-r-0 sm:last:pr-0">
      <Icon className="mt-0.5 size-4 shrink-0 text-emerald-700" />
      <div>
        <div className="text-xs font-semibold text-slate-950">{title}</div>
        <p className="mt-1 text-xs leading-5 text-slate-600">{copy}</p>
      </div>
    </div>
  )
}

function InfoPage({ page }: { page: InfoPageId }) {
  const content = infoPages[page]

  return (
    <div className="min-h-screen bg-white text-slate-950">
      <PublicHeader />
      <main className="mx-auto grid max-w-[1040px] gap-8 px-4 py-10 sm:px-6 lg:grid-cols-[190px_minmax(0,1fr)] lg:py-14">
        <nav className="flex gap-1 overflow-x-auto lg:block lg:space-y-1" aria-label="Trust and operations">
          {publicLinks.map((link) => (
            <a
              className={
                link.page === page
                  ? 'inline-flex h-8 shrink-0 items-center rounded-md bg-blue-50 px-2.5 text-xs font-semibold text-blue-700 lg:flex'
                  : 'inline-flex h-8 shrink-0 items-center rounded-md px-2.5 text-xs font-medium text-slate-600 hover:bg-slate-50 hover:text-slate-950 lg:flex'
              }
              href={link.href}
              aria-current={link.page === page ? 'page' : undefined}
              key={link.page}
            >
              {link.label}
            </a>
          ))}
        </nav>
        <article className="min-w-0">
          <h1 className="text-4xl font-semibold tracking-normal">{content.title}</h1>
          <p className="mt-4 max-w-2xl text-sm leading-6 text-slate-600">{content.summary}</p>
          <div className="mt-8 border-t border-slate-200">
            {content.rows.map((row) => (
              <section className="grid gap-2 border-b border-slate-200 py-5 sm:grid-cols-[150px_minmax(0,1fr)]" key={row.label}>
                <h2 className="text-xs font-semibold text-slate-950">{row.label}</h2>
                <p className="text-xs leading-5 text-slate-600">{row.value}</p>
              </section>
            ))}
          </div>
          <div className="mt-7 flex flex-wrap gap-2">
            {content.primaryAction ? (
              <Button asChild>
                <a href={content.primaryAction.href}>
                  {content.primaryAction.label}
                  <ArrowRight className="size-3.5" />
                </a>
              </Button>
            ) : null}
            {content.secondaryAction ? (
              <Button asChild variant="secondary">
                <a href={content.secondaryAction.href}>{content.secondaryAction.label}</a>
              </Button>
            ) : null}
          </div>
        </article>
      </main>
      <PublicFooter />
    </div>
  )
}

function PublicFooter() {
  return (
    <footer className="border-t border-slate-200 bg-white">
      <div className="mx-auto flex max-w-[1180px] flex-col gap-3 px-4 py-6 text-xs text-slate-500 sm:flex-row sm:items-center sm:justify-between sm:px-6">
        <span>VassilStudio local-first voice workspace</span>
        <nav className="flex flex-wrap gap-x-4 gap-y-2" aria-label="Footer navigation">
          {publicLinks.map((link) => (
            <a className="hover:text-slate-950" href={link.href} key={link.page}>{link.label}</a>
          ))}
        </nav>
      </div>
    </footer>
  )
}
