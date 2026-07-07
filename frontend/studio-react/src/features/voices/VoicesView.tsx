import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  ArrowRight,
  Edit3,
  FileAudio,
  FolderPlus,
  Languages,
  Loader2,
  Mic2,
  RefreshCw,
  Save,
  Search,
  Trash2,
  Waves,
  X,
} from 'lucide-react'

import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { QueryErrorState } from '@/components/ui/query-error'
import { useToast } from '@/components/ui/use-toast'
import { api, type ImportCandidate, type Voice } from '@/lib/api'
import { formatBytes, formatDuration } from '@/lib/format'
import {
  VOICE_LANGUAGES,
  normalizeVoiceLanguage,
  type VoiceLanguage,
  voiceLanguageLabel,
  voiceLanguageShortLabel,
} from '@/lib/language'
import { queryErrorMessage } from '@/lib/query-error'
import { setPreferredLanguage, setPreferredVoiceId } from '@/lib/studio-preferences'

export function VoicesView() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const [search, setSearch] = useState('')
  const [editingVoiceId, setEditingVoiceId] = useState('')
  const [editName, setEditName] = useState('')
  const [editLanguage, setEditLanguage] = useState<VoiceLanguage>('vi')
  const [editReferenceText, setEditReferenceText] = useState('')
  const [importLanguage, setImportLanguage] = useState<VoiceLanguage>('vi')
  const [importReferenceText, setImportReferenceText] = useState('')
  const [deleteTarget, setDeleteTarget] = useState<Voice | null>(null)

  const voicesQuery = useQuery({ queryKey: ['voices'], queryFn: api.voices })
  const importCandidatesQuery = useQuery({
    queryKey: ['voice-import-candidates'],
    queryFn: api.importCandidates,
  })
  const modelStatusQuery = useQuery({
    queryKey: ['model-status'],
    queryFn: api.modelStatus,
    staleTime: 30000,
    refetchInterval: 30000,
  })

  const importVoiceMutation = useMutation({
    mutationFn: ({
      filename,
      name,
      language,
      referenceText,
      autoTranscribe,
    }: {
      filename: string
      name: string
      language: VoiceLanguage
      referenceText?: string
      autoTranscribe: boolean
    }) => api.importVoiceCandidate(filename, { name, language, referenceText, autoTranscribe }),
    onSuccess: (voice) => {
      void queryClient.invalidateQueries({ queryKey: ['voices'] })
      void queryClient.invalidateQueries({ queryKey: ['voice-import-candidates'] })
      setImportReferenceText('')
      toast({
        title: 'Voice profile ready',
        description: `${voice.name} was imported and can be used in Generate.`,
        variant: 'success',
      })
    },
    onError: (error) => {
      toast({
        title: 'Import failed',
        description: error instanceof Error ? error.message : 'Unable to import voice.',
        variant: 'danger',
      })
    },
  })

  const updateVoiceMutation = useMutation({
    mutationFn: ({
      voiceId,
      name,
      language,
      referenceText,
    }: {
      voiceId: string
      name: string
      language: VoiceLanguage
      referenceText: string
    }) => api.updateVoice(voiceId, { name, language, referenceText }),
    onSuccess: (voice) => {
      void queryClient.invalidateQueries({ queryKey: ['voices'] })
      setEditingVoiceId('')
      toast({
        title: 'Voice updated',
        description: `${voice.name} metadata was saved.`,
        variant: 'success',
      })
    },
    onError: (error) => {
      toast({
        title: 'Update failed',
        description: error instanceof Error ? error.message : 'Unable to update voice.',
        variant: 'danger',
      })
    },
  })

  const deleteVoiceMutation = useMutation({
    mutationFn: api.deleteVoice,
    onSuccess: (result) => {
      void queryClient.invalidateQueries({ queryKey: ['voices'] })
      setDeleteTarget(null)
      toast({
        title: 'Voice deleted',
        description: `Removed profile ${result.voice_id}.`,
        variant: 'success',
      })
    },
    onError: (error) => {
      toast({
        title: 'Delete failed',
        description: error instanceof Error ? error.message : 'Unable to delete voice.',
        variant: 'danger',
      })
    },
  })

  const voices = useMemo(() => voicesQuery.data ?? [], [voicesQuery.data])
  const candidates = useMemo(() => importCandidatesQuery.data ?? [], [importCandidatesQuery.data])
  const voicesError = voicesQuery.isError
    ? queryErrorMessage(voicesQuery.error, 'Unable to load saved voice profiles.')
    : null
  const candidatesError = importCandidatesQuery.isError
    ? queryErrorMessage(importCandidatesQuery.error, 'Unable to load import candidates.')
    : null
  const normalizedSearch = search.trim().toLowerCase()
  const filteredVoices = useMemo(
    () =>
      voices.filter((voice) => {
        if (!normalizedSearch) {
          return true
        }
        return [voice.name, voice.voice_id, voice.language, voice.reference_text, voice.reference_text_source]
          .join(' ')
          .toLowerCase()
          .includes(normalizedSearch)
      }),
    [normalizedSearch, voices],
  )
  const filteredCandidates = useMemo(
    () =>
      candidates.filter((candidate) => {
        if (!normalizedSearch) {
          return true
        }
        return [candidate.name, candidate.filename].join(' ').toLowerCase().includes(normalizedSearch)
      }),
    [candidates, normalizedSearch],
  )
  const importRuntimeLanguageWarning = getRuntimeLanguageWarning(
    importLanguage,
    modelStatusQuery.data?.runtime.asr_configured_languages,
  )

  const startEdit = (voice: Voice) => {
    setEditingVoiceId(voice.voice_id)
    setEditName(voice.name)
    setEditLanguage(normalizeVoiceLanguage(voice.language))
    setEditReferenceText(voice.reference_text)
  }

  const saveEdit = (voice: Voice) => {
    updateVoiceMutation.mutate({
      voiceId: voice.voice_id,
      name: editName,
      language: editLanguage,
      referenceText: editReferenceText,
    })
  }

  const handleUseInGenerate = (voice: Voice) => {
    setPreferredVoiceId(voice.voice_id)
    setPreferredLanguage(normalizeVoiceLanguage(voice.language))
    toast({
      title: 'Voice selected',
      description: `${voice.name} will be used in Generate.`,
      variant: 'success',
    })
    window.location.hash = '/generate'
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-col gap-2 rounded-md border border-slate-200 bg-white p-2 sm:flex-row sm:items-center">
        <label className="flex min-h-8 min-w-0 flex-1 items-center gap-2 rounded-md border border-slate-200 bg-white px-2.5">
          <Search className="size-4 text-slate-500" />
          <span className="sr-only">Search voices</span>
          <input
            className="min-w-0 flex-1 bg-transparent text-xs font-medium text-slate-900 outline-none placeholder:text-slate-500"
            value={search}
            placeholder="Search voices or files"
            onChange={(event) => setSearch(event.target.value)}
          />
          {search ? (
            <button
              className="grid size-7 place-items-center rounded-md text-slate-500 hover:bg-white hover:text-slate-900"
              type="button"
              aria-label="Clear search"
              onClick={() => setSearch('')}
            >
              <X className="size-4" />
            </button>
          ) : null}
        </label>
        <Button
          className="self-start sm:self-auto"
          variant="secondary"
          onClick={() => {
            void voicesQuery.refetch()
            void importCandidatesQuery.refetch()
          }}
        >
          <RefreshCw className="size-4" />
          Refresh
        </Button>
      </div>

      <div className="grid min-w-0 grid-cols-1 gap-3 xl:grid-cols-[minmax(0,1fr)_360px]">
        <Card>
          <CardHeader>
            <div>
              <div className="text-sm font-semibold text-slate-950">Saved profiles</div>
              <div className="mt-1 text-xs text-slate-600">Local voice profiles available for rendering.</div>
            </div>
          </CardHeader>
          <CardContent>
            {voicesError ? (
              <QueryErrorState
                title="Unable to load voices"
                message={voicesError}
                onRetry={() => {
                  void voicesQuery.refetch()
                }}
              />
            ) : voicesQuery.isLoading ? (
              <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                {Array.from({ length: 4 }).map((_, index) => (
                  <div key={index} className="h-36 animate-pulse rounded-md bg-slate-100" />
                ))}
              </div>
            ) : filteredVoices.length > 0 ? (
              <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
                {filteredVoices.map((voice) => (
                  <VoiceCard
                    key={voice.voice_id}
                    voice={voice}
                    editing={editingVoiceId === voice.voice_id}
                    editName={editName}
                    editLanguage={editLanguage}
                    editReferenceText={editReferenceText}
                    saving={updateVoiceMutation.isPending}
                    onEdit={() => startEdit(voice)}
                    onCancelEdit={() => setEditingVoiceId('')}
                    onDelete={() => setDeleteTarget(voice)}
                    onSave={() => saveEdit(voice)}
                    onUse={() => handleUseInGenerate(voice)}
                    onNameChange={setEditName}
                    onLanguageChange={setEditLanguage}
                    onReferenceTextChange={setEditReferenceText}
                  />
                ))}
              </div>
            ) : (
              <EmptyState
                icon={Mic2}
                title={voices.length > 0 ? 'No matching voices' : 'No saved profiles'}
                copy={
                  voices.length > 0
                    ? 'Adjust the search term to find another saved profile.'
                    : 'Prepare a reference recording to make it available in Generate.'
                }
              />
            )}
          </CardContent>
        </Card>

        <ImportCandidatesPanel
          candidates={filteredCandidates}
          importingFilename={importVoiceMutation.variables?.filename}
          importing={importVoiceMutation.isPending}
          language={importLanguage}
          referenceText={importReferenceText}
          runtimeLanguageWarning={importRuntimeLanguageWarning}
          error={candidatesError}
          totalCandidates={candidates.length}
          onRetry={() => {
            void importCandidatesQuery.refetch()
          }}
          onLanguageChange={setImportLanguage}
          onReferenceTextChange={setImportReferenceText}
          onImport={(candidate) =>
            {
              const referenceText = importReferenceText.trim()
              if (!referenceText && importRuntimeLanguageWarning) {
                toast({
                  title: 'Reference text required',
                  description: `${voiceLanguageLabel(importLanguage)} ASR is not configured. Paste a matching transcript or choose another language.`,
                  variant: 'danger',
                })
                return
              }
              importVoiceMutation.mutate({
                filename: candidate.filename,
                name: candidate.name,
                language: importLanguage,
                referenceText: referenceText || undefined,
                autoTranscribe: !referenceText,
              })
            }
          }
        />
      </div>

      <ConfirmDialog
        open={Boolean(deleteTarget)}
        title="Delete voice profile?"
        description={
          deleteTarget
            ? `This removes "${deleteTarget.name}" from the local voice library. The source candidate file is not deleted.`
            : ''
        }
        confirmLabel="Delete voice"
        busy={deleteVoiceMutation.isPending}
        onOpenChange={(open) => {
          if (!open) {
            setDeleteTarget(null)
          }
        }}
        onConfirm={() => {
          if (deleteTarget) {
            deleteVoiceMutation.mutate(deleteTarget.voice_id)
          }
        }}
      />
    </div>
  )
}

function VoiceCard({
  voice,
  editing,
  editName,
  editLanguage,
  editReferenceText,
  saving,
  onEdit,
  onCancelEdit,
  onDelete,
  onSave,
  onUse,
  onNameChange,
  onLanguageChange,
  onReferenceTextChange,
}: {
  voice: Voice
  editing: boolean
  editName: string
  editLanguage: VoiceLanguage
  editReferenceText: string
  saving: boolean
  onEdit: () => void
  onCancelEdit: () => void
  onDelete: () => void
  onSave: () => void
  onUse: () => void
  onNameChange: (value: string) => void
  onLanguageChange: (value: VoiceLanguage) => void
  onReferenceTextChange: (value: string) => void
}) {
  return (
    <article className="min-w-0 overflow-hidden rounded-md border border-slate-200 bg-white p-2.5 transition-colors hover:border-sky-300 hover:bg-sky-50/20">
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2.5">
          <div className="grid size-8 shrink-0 place-items-center rounded-md bg-gradient-to-br from-sky-400 via-blue-600 to-fuchsia-500 text-xs font-semibold text-white">
            {voice.name.slice(0, 1).toUpperCase()}
          </div>
          <div className="min-w-0">
            <div className="truncate text-sm font-semibold text-slate-950">{voice.name}</div>
            <div className="mt-1 flex max-w-full items-center gap-1.5">
              <span
                className="shrink-0 rounded-full border border-slate-200 bg-slate-50 px-1.5 py-0.5 text-[10px] font-bold text-slate-600"
                title={voiceLanguageLabel(voice.language)}
              >
                {voiceLanguageShortLabel(voice.language)}
              </span>
              <div
                className="inline-flex min-w-0 items-center gap-1.5 rounded-full border border-slate-200 bg-white px-2 py-0.5 text-xs font-medium text-slate-500"
                title={voice.voice_id}
              >
                <code className="truncate font-mono text-[10px] text-slate-600">{shortVoiceId(voice.voice_id)}</code>
              </div>
            </div>
          </div>
        </div>
      </div>

      {editing ? (
        <div className="mt-4 space-y-3">
          <label className="block">
            <span className="mb-1.5 block text-xs font-semibold text-slate-600">Name</span>
            <input
              className="h-8 w-full rounded-md border border-slate-200 px-2.5 text-xs font-medium text-slate-950 outline-none focus:border-blue-400 focus:ring-2 focus:ring-sky-100"
              value={editName}
              onChange={(event) => onNameChange(event.target.value)}
            />
          </label>
          <label className="block">
            <span className="mb-1.5 flex items-center gap-1.5 text-xs font-semibold text-slate-600">
              <Languages className="size-3.5" />
              Language
            </span>
            <select
              className="h-8 w-full rounded-md border border-slate-200 bg-white px-2.5 text-xs font-medium text-slate-950 outline-none focus:border-blue-400 focus:ring-2 focus:ring-sky-100"
              value={editLanguage}
              onChange={(event) => onLanguageChange(normalizeVoiceLanguage(event.target.value))}
            >
              {VOICE_LANGUAGES.map((language) => (
                <option key={language.value} value={language.value}>
                  {language.label}
                </option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className="mb-1.5 block text-xs font-semibold text-slate-600">Reference text</span>
            <textarea
              className="min-h-24 w-full resize-y rounded-md border border-slate-200 px-3 py-2 text-sm leading-6 text-slate-950 outline-none focus:border-blue-400 focus:ring-2 focus:ring-sky-100"
              value={editReferenceText}
              onChange={(event) => onReferenceTextChange(event.target.value)}
            />
          </label>
          <div className="flex flex-wrap gap-2">
            <Button size="sm" disabled={saving} onClick={onSave}>
              {saving ? <Loader2 className="size-4 animate-spin" /> : <Save className="size-4" />}
              Save
            </Button>
            <Button size="sm" variant="secondary" onClick={onCancelEdit}>
              Cancel
            </Button>
          </div>
        </div>
      ) : (
        <>
          <p className="mt-2.5 line-clamp-2 min-h-10 break-words text-xs leading-5 text-slate-700">
            {voice.reference_text || 'No reference text saved yet.'}
          </p>
          <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
            <VoiceMeta label="Duration" value={formatDuration(voice.duration_seconds)} />
            <VoiceMeta label="Size" value={formatBytes(voice.audio_size_bytes)} />
          </div>
          {voice.reference_audio_url ? (
            <audio className="mt-3 h-9 w-full" controls src={voice.reference_audio_url} />
          ) : null}
          <div className="mt-3 flex flex-wrap gap-2">
            <Button className="min-w-24" size="sm" onClick={onUse}>
              <ArrowRight className="size-4" />
              Use
            </Button>
            <Button size="sm" variant="secondary" onClick={onEdit}>
              <Edit3 className="size-4" />
              Edit
            </Button>
            <Button
              size="sm"
              variant="secondary"
              className="w-8 border-red-200 px-0 text-red-700 hover:bg-red-50 hover:text-red-800"
              onClick={onDelete}
              aria-label="Delete voice"
              title="Delete voice"
            >
              <Trash2 className="size-4" />
            </Button>
          </div>
        </>
      )}
    </article>
  )
}

function shortVoiceId(voiceId: string) {
  if (voiceId.length <= 12) {
    return voiceId
  }
  return `${voiceId.slice(0, 8)}...${voiceId.slice(-4)}`
}

function ImportCandidatesPanel({
  candidates,
  totalCandidates,
  importing,
  importingFilename,
  language,
  referenceText,
  runtimeLanguageWarning,
  error,
  onRetry,
  onLanguageChange,
  onReferenceTextChange,
  onImport,
}: {
  candidates: ImportCandidate[]
  totalCandidates: number
  importing: boolean
  importingFilename?: string
  language: VoiceLanguage
  referenceText: string
  runtimeLanguageWarning: string | null
  error: string | null
  onRetry: () => void
  onLanguageChange: (language: VoiceLanguage) => void
  onReferenceTextChange: (value: string) => void
  onImport: (candidate: ImportCandidate) => void
}) {
  return (
    <Card>
      <CardHeader>
        <div>
          <div className="text-sm font-semibold text-slate-950">Import candidates</div>
          <div className="mt-1 text-xs text-slate-600">Reference audio waiting to become voice profiles.</div>
        </div>
        <FolderPlus className="size-5 text-slate-500" />
      </CardHeader>
      <CardContent className="space-y-3">
        <label className="block">
          <span className="mb-1.5 flex items-center gap-1.5 text-xs font-semibold text-slate-600">
            <Languages className="size-3.5" />
            New profile language
          </span>
          <select
            className="h-8 w-full rounded-md border border-slate-200 bg-white px-2.5 text-xs font-medium text-slate-950 outline-none focus:border-blue-400 focus:ring-2 focus:ring-sky-100"
            value={language}
            onChange={(event) => onLanguageChange(normalizeVoiceLanguage(event.target.value))}
          >
            {VOICE_LANGUAGES.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>
          <p className="mt-1.5 text-xs leading-5 text-slate-500">
            Leave reference text empty to auto-transcribe with the selected local ASR model.
          </p>
        </label>
        {runtimeLanguageWarning ? (
          <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs font-medium leading-5 text-amber-800">
            {runtimeLanguageWarning} Paste a transcript to import without ASR.
          </div>
        ) : null}
        <label className="block">
          <span className="mb-1.5 block text-xs font-semibold text-slate-600">
            Reference text (optional)
          </span>
          <textarea
            className="min-h-20 w-full resize-y rounded-md border border-slate-200 px-3 py-2 text-xs leading-5 text-slate-950 outline-none placeholder:text-slate-400 focus:border-blue-400 focus:ring-2 focus:ring-sky-100"
            value={referenceText}
            placeholder={
              language === 'en'
                ? 'Paste the exact English transcript, or leave empty for English ASR.'
                : 'Paste transcript to override Vietnamese ASR.'
            }
            onChange={(event) => onReferenceTextChange(event.target.value)}
          />
        </label>
        {error ? (
          <QueryErrorState compact title="Unable to load files" message={error} onRetry={onRetry} />
        ) : candidates.length > 0 ? (
          candidates.map((candidate) => (
            <div key={candidate.filename} className="min-w-0 overflow-hidden rounded-md border border-slate-200 bg-white p-3">
              <div className="flex items-start gap-3">
                <div className="grid size-8 shrink-0 place-items-center rounded-md bg-gradient-to-br from-sky-400 via-blue-600 to-fuchsia-500 text-white">
                  <FileAudio className="size-4" />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-semibold text-slate-950">{candidate.name}</div>
                  <div className="mt-1 truncate text-xs text-slate-500">{candidate.filename}</div>
                </div>
                <Badge variant="warning">{formatBytes(candidate.size_bytes)}</Badge>
              </div>
              {candidate.audio_url ? <audio className="mt-3 h-9 w-full" controls src={candidate.audio_url} /> : null}
              <Button
                className="mt-3 w-full"
                disabled={importing && importingFilename === candidate.filename}
                onClick={() => onImport(candidate)}
              >
                {importing && importingFilename === candidate.filename ? (
                  <Loader2 className="size-4 animate-spin" />
                ) : (
                  <Waves className="size-4" />
                )}
                {importing && importingFilename === candidate.filename ? 'Preparing' : 'Prepare profile'}
              </Button>
            </div>
          ))
        ) : (
          <EmptyState
            icon={FolderPlus}
            title={totalCandidates > 0 ? 'No matching files' : 'No files waiting'}
            copy={
              totalCandidates > 0
                ? 'Adjust the search term to find another import candidate.'
                : 'Place WAV, WEBM, or WEBA reference clips in data/voices to prepare them here.'
            }
          />
        )}
      </CardContent>
    </Card>
  )
}

function VoiceMeta({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-slate-200 bg-white px-2.5 py-1.5">
      <div className="text-xs font-semibold text-slate-900">{value}</div>
      <div className="mt-0.5 text-xs font-medium text-slate-500">{label}</div>
    </div>
  )
}

function EmptyState({
  icon: Icon,
  title,
  copy,
}: {
  icon: typeof Mic2
  title: string
  copy: string
}) {
  return (
    <div className="rounded-md border border-dashed border-slate-300 bg-white p-4 text-center">
      <Icon className="mx-auto size-6 text-slate-400" />
      <div className="mt-2 text-sm font-semibold text-slate-900">{title}</div>
      <p className="mx-auto mt-1 max-w-sm text-xs leading-5 text-slate-500">{copy}</p>
    </div>
  )
}

function getRuntimeLanguageWarning(
  selectedLanguage: VoiceLanguage,
  configuredLanguages: string[] | undefined,
) {
  if (!configuredLanguages?.length) {
    return null
  }

  const configured = new Set(configuredLanguages.map((language) => normalizeVoiceLanguage(language)))
  if (configured.has(selectedLanguage)) {
    return null
  }

  const available = Array.from(configured)
    .map((language) => voiceLanguageLabel(language))
    .join(', ')
  return `${voiceLanguageLabel(selectedLanguage)} ASR is not configured on this backend. Available runtime: ${available}.`
}
