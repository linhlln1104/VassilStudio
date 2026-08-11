import { useEffect, useRef, useState } from 'react'
import {
  ArrowDown,
  ArrowRight,
  AudioLines,
  Captions,
  Cpu,
  Download,
  Gauge,
  HardDrive,
  LockKeyhole,
  Mic,
  PenLine,
  Upload,
  UsersRound,
  type LucideIcon,
} from 'lucide-react'

import { Button } from '@/components/ui/button'
import { BRAND_LOGO_SRC, BRAND_NAME } from '@/lib/brand'
import { VoiceprintCanvas } from './VoiceprintCanvas'

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

type ShowcaseItem = {
  id: 'generate' | 'transcribe' | 'realtime' | 'voices'
  label: string
  title: string
  copy: string
  image: string
  alt: string
  icon: LucideIcon
}

const publicLinks: Array<{ label: string; href: string; page: InfoPageId }> = [
  { label: 'Operations', href: '/operations', page: 'operations' },
  { label: 'Changelog', href: '/changelog', page: 'changelog' },
  { label: 'Support', href: '/support', page: 'support' },
  { label: 'Privacy', href: '/privacy', page: 'privacy' },
  { label: 'License', href: '/license', page: 'license' },
]

const productLinks = [
  { label: 'Product', href: '/#product' },
  { label: 'Workflow', href: '/#workflow' },
  { label: 'Local runtime', href: '/#local-runtime' },
  { label: 'Operations', href: '/operations' },
]

const workflowSteps: Array<{ step: string; title: string; copy: string; icon: LucideIcon }> = [
  {
    step: '01',
    title: 'Save a voice',
    copy: 'Import clean reference audio as a reusable local profile.',
    icon: Upload,
  },
  {
    step: '02',
    title: 'Add your source',
    copy: 'Write a script, upload a recording, or start the microphone.',
    icon: PenLine,
  },
  {
    step: '03',
    title: 'Run locally',
    copy: 'Choose Vietnamese or English and keep model state visible.',
    icon: Cpu,
  },
  {
    step: '04',
    title: 'Review the output',
    copy: 'Listen, copy, download, retry, or trace the completed job.',
    icon: Download,
  },
]

const showcaseItems: ShowcaseItem[] = [
  {
    id: 'generate',
    label: 'Generate',
    title: 'Turn a script into a controlled voice render',
    copy: 'Select a saved profile, set language and render mode, then review every output in the same queue.',
    image: '/studio/brand/vassil-studio-generate.png',
    alt: 'VassilStudio Generate workspace with script editor, voice controls, and output queue',
    icon: AudioLines,
  },
  {
    id: 'transcribe',
    label: 'Transcribe',
    title: 'Move from local recording to reusable transcript',
    copy: 'Validate an audio file before queueing ZipFormer ASR, then send the finished transcript directly into Generate.',
    image: '/studio/brand/vassil-studio-transcribe.png',
    alt: 'VassilStudio Transcribe workspace with audio upload and transcript preview',
    icon: Captions,
  },
  {
    id: 'realtime',
    label: 'Realtime',
    title: 'Follow microphone speech as one live session',
    copy: 'Keep websocket, microphone, model, and segment state visible while the final transcript is assembled locally.',
    image: '/studio/brand/vassil-studio-realtime.png',
    alt: 'VassilStudio Realtime workspace with session status and live transcript',
    icon: Mic,
  },
  {
    id: 'voices',
    label: 'Voices',
    title: 'Keep reference voices ready for repeat work',
    copy: 'Store language, transcript, duration, sample rate, and source audio together in a reusable voice profile.',
    image: '/studio/brand/vassil-studio-voices.png',
    alt: 'VassilStudio Voices workspace with saved profile and reference audio import',
    icon: UsersRound,
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
      <PublicHeader showProgress />
      <main>
        <section
          id="product"
          data-qa="landing-hero"
          className="relative h-[calc(100svh-300px)] min-h-[520px] max-h-[650px] overflow-hidden border-b border-slate-200 bg-white"
        >
          <VoiceprintCanvas />
          <div className="pointer-events-none absolute inset-0 mx-auto max-w-[1180px] px-4 font-mono text-[10px] text-slate-400 sm:px-6" aria-hidden="true">
            <span className="absolute left-4 top-5 sm:left-6">SYSTEM / 00</span>
            <span className="absolute right-4 top-5 sm:right-6">VI + EN / LOCAL</span>
          </div>
          <div
            data-qa="hero-content"
            className="relative mx-auto flex h-full max-w-[1180px] px-4 pt-14 sm:px-6 sm:pt-16"
          >
            <div className="max-w-[760px]">
              <div className="flex items-center gap-2 text-xs font-semibold text-blue-700">
                <span className="size-1.5 bg-emerald-500" aria-hidden="true" />
                Local voice system
              </div>
              <h1 className="mt-3 text-5xl font-semibold tracking-normal text-slate-950 sm:text-7xl">
                VassilStudio
              </h1>
              <p className="mt-3 max-w-2xl text-2xl font-medium leading-tight text-slate-950 sm:text-3xl">
                Voice in. Voice out. Nothing leaves your machine.
              </p>
              <p className="mt-3 max-w-xl text-sm leading-6 text-slate-600">
                Generate, transcribe, and reuse voices with local Vietnamese and English models.
              </p>
              <div className="mt-6 flex flex-wrap gap-2">
                <Button asChild size="lg">
                  <a href="/studio">
                    Open Studio
                    <ArrowRight className="size-4" />
                  </a>
                </Button>
                <Button asChild size="lg" variant="secondary">
                  <a href="#workflow">
                    See the workflow
                    <ArrowDown className="size-4" />
                  </a>
                </Button>
              </div>
            </div>
          </div>
        </section>

        <section className="border-b border-slate-200 bg-slate-50" aria-label="Product foundation">
          <div className="relative mx-auto max-w-[1180px] px-4 sm:px-6">
            <figure
              data-qa="product-stage"
              className="relative z-10 -mt-16 aspect-[36/25] overflow-hidden rounded-sm border border-slate-300 bg-white"
            >
              <img
                className="size-full object-cover object-top"
                src="/studio/brand/vassil-studio-generate.png"
                alt="VassilStudio Generate workspace with script, voice, and output controls"
                loading="eager"
              />
            </figure>
            <div className="grid grid-cols-1 pt-4 sm:grid-cols-2 lg:grid-cols-4">
              <FoundationItem icon={HardDrive} title="Local by default" copy="Configured workspace paths" />
              <FoundationItem icon={Captions} title="ZipFormer ASR" copy="File and realtime recognition" />
              <FoundationItem icon={AudioLines} title="ZipVoice TTS" copy="Reusable reference voices" />
              <FoundationItem icon={LockKeyhole} title="Operator controlled" copy="Auth, diagnostics, cleanup" />
            </div>
          </div>
        </section>

        <section id="workflow" className="scroll-mt-16 border-b border-slate-200 bg-white">
          <div className="mx-auto max-w-[1180px] px-4 py-14 sm:px-6 sm:py-18">
            <div className="max-w-2xl">
              <div className="font-mono text-xs font-semibold text-blue-700">01 / Workflow</div>
              <h2 className="mt-2 text-3xl font-semibold tracking-normal text-slate-950">
                One local loop from source to output
              </h2>
              <p className="mt-3 text-sm leading-6 text-slate-600">
                The work stays legible from the first reference clip through model readiness, queue state, and final output.
              </p>
            </div>

            <div className="mt-8 grid grid-cols-1 border-y border-slate-200 sm:grid-cols-2 lg:grid-cols-4">
              {workflowSteps.map((item) => (
                <article
                  className="border-b border-slate-200 py-5 last:border-b-0 sm:px-4 sm:[&:nth-child(n+3)]:border-b-0 sm:[&:nth-child(odd)]:border-r lg:border-b-0 lg:border-r lg:first:pl-0 lg:last:border-r-0 lg:last:pr-0"
                  key={item.step}
                >
                  <div className="flex items-center justify-between gap-3">
                    <item.icon className="size-5 text-blue-700" />
                    <span className="font-mono text-xs text-slate-400">{item.step}</span>
                  </div>
                  <h3 className="mt-5 text-sm font-semibold text-slate-950">{item.title}</h3>
                  <p className="mt-1 text-xs leading-5 text-slate-600">{item.copy}</p>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section className="border-b border-slate-200 bg-slate-50">
          <div className="mx-auto max-w-[1180px] px-4 py-14 sm:px-6 sm:py-18">
            <div className="max-w-2xl">
              <div className="font-mono text-xs font-semibold text-blue-700">02 / Product</div>
              <h2 className="mt-2 text-3xl font-semibold tracking-normal text-slate-950">
                The actual workspace, not a mockup
              </h2>
              <p className="mt-3 text-sm leading-6 text-slate-600">
                Every view uses the same language state, runtime readiness, job history, and local storage boundaries.
              </p>
            </div>
            <ProductShowcase />
          </div>
        </section>

        <section id="local-runtime" className="scroll-mt-16 border-b border-slate-200 bg-white">
          <div className="mx-auto grid max-w-[1180px] gap-10 px-4 py-14 sm:px-6 sm:py-18 lg:grid-cols-[minmax(0,0.8fr)_minmax(0,1fr)] lg:gap-18">
            <div className="max-w-lg">
              <div className="font-mono text-xs font-semibold text-emerald-700">03 / Runtime</div>
              <h2 className="mt-2 text-3xl font-semibold tracking-normal text-slate-950">
                Your audio stays where you put it
              </h2>
              <p className="mt-4 text-sm leading-6 text-slate-600">
                VassilStudio keeps model execution, voice profiles, source audio, transcripts, and outputs under operator-configured local paths.
              </p>
              <Button asChild className="mt-6" variant="secondary">
                <a href="/privacy">
                  Review privacy details
                  <ArrowRight className="size-4" />
                </a>
              </Button>
            </div>
            <div className="border-t border-slate-200">
              <LocalControlRow
                icon={HardDrive}
                title="Explicit storage"
                copy="Voices, uploads, jobs, outputs, logs, and authentication data have visible local boundaries."
              />
              <LocalControlRow
                icon={Gauge}
                title="Readiness before work"
                copy="Cold models, missing language assets, queue state, and runtime diagnostics stay visible in context."
              />
              <LocalControlRow
                icon={LockKeyhole}
                title="No cloud account required"
                copy="Local owner authentication and optional API keys protect the workspace without external identity services."
              />
            </div>
          </div>
        </section>

        <section className="bg-slate-950 text-white">
          <div className="mx-auto flex max-w-[1180px] flex-col gap-6 px-4 py-10 sm:flex-row sm:items-center sm:justify-between sm:px-6">
            <div>
              <div className="mb-2 font-mono text-xs font-semibold text-cyan-300">04 / Studio</div>
              <h2 className="text-xl font-semibold tracking-normal">Start with the workspace you already own</h2>
              <p className="mt-2 text-sm leading-6 text-slate-300">
                Open Studio to create a voice profile, generate audio, or transcribe a recording.
              </p>
            </div>
            <div className="flex shrink-0 flex-wrap gap-2">
              <Button asChild className="bg-white text-blue-800 hover:bg-blue-50" size="lg">
                <a href="/studio">
                  Open Studio
                  <ArrowRight className="size-4" />
                </a>
              </Button>
              <Button asChild className="border-slate-600 bg-transparent text-white hover:border-white hover:bg-slate-900" size="lg" variant="secondary">
                <a href="/operations">Operations guide</a>
              </Button>
            </div>
          </div>
        </section>
      </main>
      <PublicFooter />
    </div>
  )
}

function ProductShowcase() {
  const [activeId, setActiveId] = useState<ShowcaseItem['id']>('voices')
  const activeItem = showcaseItems.find((item) => item.id === activeId) ?? showcaseItems[0]

  return (
    <div className="mt-8">
      <div className="grid grid-cols-2 border-b border-slate-200 sm:flex" role="tablist" aria-label="Studio workspace preview">
        {showcaseItems.map((item) => (
          <button
            className={
              item.id === activeId
                ? 'inline-flex h-11 shrink-0 items-center gap-2 border-b-2 border-blue-700 px-3 text-xs font-semibold text-blue-800'
                : 'inline-flex h-11 shrink-0 items-center gap-2 border-b-2 border-transparent px-3 text-xs font-medium text-slate-500 hover:text-slate-950'
            }
            type="button"
            role="tab"
            aria-controls="studio-showcase-panel"
            aria-selected={item.id === activeId}
            onClick={() => setActiveId(item.id)}
            key={item.id}
          >
            <item.icon className="size-4" />
            {item.label}
          </button>
        ))}
      </div>

      <div
        id="studio-showcase-panel"
        className="pt-5"
        role="tabpanel"
        aria-label={`${activeItem.label} workspace`}
      >
        <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div className="max-w-2xl">
            <h3 className="text-lg font-semibold text-slate-950">{activeItem.title}</h3>
            <p className="mt-2 text-sm leading-6 text-slate-600">{activeItem.copy}</p>
          </div>
          <Button asChild className="shrink-0 self-start" variant="secondary">
            <a href={`/studio#/${activeItem.id}`}>
              Open {activeItem.label}
              <ArrowRight className="size-4" />
            </a>
          </Button>
        </div>
        <figure className="mt-5 aspect-[36/25] overflow-hidden rounded-sm border border-slate-300 bg-white">
          <img
            className="size-full object-cover object-top"
            src={activeItem.image}
            alt={activeItem.alt}
            loading="lazy"
          />
        </figure>
      </div>
    </div>
  )
}

function PublicHeader({ showProgress = false }: { showProgress?: boolean }) {
  return (
    <header className="sticky top-0 z-20 border-b border-slate-200 bg-white/95">
      <div className="mx-auto flex h-14 max-w-[1180px] items-center justify-between gap-4 px-4 sm:px-6">
        <a className="inline-flex min-w-0 items-center" href="/" aria-label="VassilStudio home">
          <img className="h-8 w-auto max-w-[150px]" src={BRAND_LOGO_SRC} alt={BRAND_NAME} />
        </a>
        <nav className="hidden items-center gap-5 text-xs font-medium text-slate-500 lg:flex" aria-label="Product navigation">
          {productLinks.map((link) => (
            <a className="hover:text-slate-950" href={link.href} key={link.href}>{link.label}</a>
          ))}
        </nav>
        <Button asChild size="sm">
          <a href="/studio">
            Open Studio
            <ArrowRight className="size-3.5" />
          </a>
        </Button>
      </div>
      {showProgress ? <ScrollProgress /> : null}
    </header>
  )
}

function ScrollProgress() {
  const indicatorRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    let animationFrame = 0

    const update = () => {
      const scrollRange = Math.max(1, document.documentElement.scrollHeight - window.innerHeight)
      const progress = Math.min(1, Math.max(0, window.scrollY / scrollRange))
      if (indicatorRef.current) indicatorRef.current.style.transform = `scaleX(${progress})`
      animationFrame = 0
    }

    const scheduleUpdate = () => {
      if (!animationFrame) animationFrame = window.requestAnimationFrame(update)
    }

    update()
    window.addEventListener('scroll', scheduleUpdate, { passive: true })
    window.addEventListener('resize', scheduleUpdate)

    return () => {
      window.cancelAnimationFrame(animationFrame)
      window.removeEventListener('scroll', scheduleUpdate)
      window.removeEventListener('resize', scheduleUpdate)
    }
  }, [])

  return (
    <div className="absolute inset-x-0 bottom-0 h-px overflow-hidden bg-slate-100" aria-hidden="true">
      <div
        ref={indicatorRef}
        data-qa="scroll-progress"
        className="h-full origin-left bg-cyan-500"
        style={{ transform: 'scaleX(0)' }}
      />
    </div>
  )
}

function FoundationItem({
  icon: Icon,
  title,
  copy,
}: {
  icon: LucideIcon
  title: string
  copy: string
}) {
  return (
    <div className="flex min-h-20 items-center gap-3 border-b border-slate-200 py-4 last:border-b-0 sm:border-r sm:px-5 sm:[&:nth-child(even)]:border-r-0 sm:[&:nth-child(n+3)]:border-b-0 lg:border-b-0 lg:[&:nth-child(even)]:border-r lg:first:pl-0 lg:last:border-r-0 lg:last:pr-0">
      <Icon className="size-4 shrink-0 text-emerald-700" />
      <div className="min-w-0">
        <div className="text-xs font-semibold text-slate-950">{title}</div>
        <p className="mt-1 text-xs leading-5 text-slate-600">{copy}</p>
      </div>
    </div>
  )
}

function LocalControlRow({
  icon: Icon,
  title,
  copy,
}: {
  icon: LucideIcon
  title: string
  copy: string
}) {
  return (
    <div className="grid gap-3 border-b border-slate-200 py-5 sm:grid-cols-[28px_160px_minmax(0,1fr)] sm:items-start">
      <Icon className="size-5 text-emerald-700" />
      <h3 className="text-sm font-semibold text-slate-950">{title}</h3>
      <p className="text-xs leading-5 text-slate-600">{copy}</p>
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
      <div className="mx-auto flex max-w-[1180px] flex-col gap-4 px-4 py-7 text-xs text-slate-500 sm:flex-row sm:items-center sm:justify-between sm:px-6">
        <a className="inline-flex items-center" href="/" aria-label="VassilStudio home">
          <img className="h-7 w-auto" src={BRAND_LOGO_SRC} alt={BRAND_NAME} />
        </a>
        <nav className="flex flex-wrap gap-x-4 gap-y-2" aria-label="Footer navigation">
          {publicLinks.map((link) => (
            <a className="hover:text-slate-950" href={link.href} key={link.page}>{link.label}</a>
          ))}
        </nav>
      </div>
    </footer>
  )
}
