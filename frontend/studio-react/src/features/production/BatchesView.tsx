import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Download, FileUp, RefreshCw } from 'lucide-react'
import { api, createIdempotencyKey } from '@/lib/api'
import { parseBatchImport, type ImportTable } from '@/lib/batch-import'
import { productionApi, downloadFile, type Batch, type BatchInput, type BatchItem, type BatchRow } from '@/lib/production-api'
import { Button } from '@/components/ui/button'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { TakeReview } from './ProjectsView'
import { useProductionAccess } from './use-production-access'
import { control, panel, Empty, Field, Loading, Pager, RequestError, Status } from './shared'

const mappingFields = ['external_id', 'text', 'language', 'voice_id', 'model_id'] as const
type Mapping = Record<typeof mappingFields[number], string>
const emptyMapping: Mapping = { external_id: '', text: '', language: '', voice_id: '', model_id: '' }
const finished = new Set(['succeeded', 'completed', 'failed', 'cancelled', 'partial_failure', 'completed_with_errors'])

export function BatchesView() {
  const { canWrite } = useProductionAccess()
  const [batchId, setBatchId] = useState(() => new URLSearchParams(window.location.hash.split('?')[1]).get('batch') ?? '')
  const [creating, setCreating] = useState(!batchId)
  const [offset, setOffset] = useState(0)
  const batches = useQuery({ queryKey: ['batches', offset], queryFn: () => productionApi.batches(offset), refetchInterval: 5000 })
  const selected = useQuery({ queryKey: ['batch', batchId], queryFn: () => productionApi.batch(batchId), enabled: Boolean(batchId), refetchInterval: (query) => !query.state.data || !finished.has(query.state.data.status) ? 1500 : 8000 })
  const open = (batch: string) => { setBatchId(batch); setCreating(false); window.history.replaceState(null, '', `#/batches?batch=${encodeURIComponent(batch)}`) }
  return <div className="space-y-4"><header className="flex flex-wrap items-center justify-between gap-3"><div><h2 className="text-lg font-semibold">Batch production</h2><p className="mt-1 text-sm text-slate-600">Validate rows before queuing. Review and export results with their source IDs.</p></div><Button disabled={!canWrite} onClick={() => setCreating(!creating)}><FileUp className="size-4" />{creating ? 'Hide import' : 'Import batch'}</Button></header>
    {creating && canWrite ? <BatchImporter onCreated={open} /> : null}
    <div className="grid min-w-0 gap-4 lg:grid-cols-[250px_minmax(0,1fr)]"><aside className={`${panel} self-start`} aria-label="Batch history"><h3 className="mb-3 text-sm font-semibold">Batch history</h3><RequestError error={batches.error} onReload={() => { void batches.refetch() }} />{batches.isLoading ? <Loading /> : batches.data?.items.length ? <div className="space-y-2">{batches.data.items.map((batch) => <button key={batch.batch_id} onClick={() => open(batch.batch_id)} className={`w-full rounded-md border p-3 text-left ${batch.batch_id === batchId ? 'border-blue-300 bg-blue-50' : 'border-slate-200 hover:bg-slate-50'}`} aria-current={batch.batch_id === batchId ? 'true' : undefined}><span className="block truncate text-sm font-semibold">{batch.name || batch.batch_id.slice(0, 8)}</span><div className="mt-2 flex items-center gap-2"><Status value={batch.status} /><span className="text-xs text-slate-500">{batch.item_count} items</span></div></button>)}</div> : <p className="text-sm text-slate-500">Your submitted batches will appear here.</p>}<Pager offset={offset} total={batches.data?.total ?? 0} size={25} onChange={setOffset} /></aside><main className="min-w-0">{selected.isLoading ? <Loading /> : selected.error ? <RequestError error={selected.error} onReload={() => { void selected.refetch() }} /> : selected.data ? <BatchMonitor key={batchId} batch={selected.data} /> : <Empty title="No batch selected">Import a file or open an existing batch to follow progress. Work continues on the server when you leave this page.</Empty>}</main></div>
  </div>
}

function BatchImporter({ onCreated }: { onCreated: (id: string) => void }) {
  const client = useQueryClient()
  const [table, setTable] = useState<ImportTable | null>(null)
  const [filename, setFilename] = useState('')
  const [importError, setImportError] = useState<Error | null>(null)
  const [mapping, setMapping] = useState<Mapping>(emptyMapping)
  const [projectId, setProjectId] = useState('')
  const [projectOffset, setProjectOffset] = useState(0)
  const [name, setName] = useState('')
  const [language, setLanguage] = useState('vi')
  const [voiceId, setVoiceId] = useState('')
  const [modelId, setModelId] = useState('')
  const [key, setKey] = useState(() => createIdempotencyKey('tts'))
  const projects = useQuery({ queryKey: ['projects', projectOffset], queryFn: () => productionApi.projects(projectOffset) })
  const voices = useQuery({ queryKey: ['voices'], queryFn: api.voices })
  const models = useQuery({ queryKey: ['tts-models'], queryFn: api.ttsModels })
  const rows: BatchRow[] = table?.records.map((record, index) => {
    const row: BatchRow = { external_id: mapping.external_id ? record[mapping.external_id] : `row-${index + 1}`, text: mapping.text ? record[mapping.text] : '' }
    for (const field of ['language', 'voice_id', 'model_id'] as const) if (mapping[field] && record[mapping[field]]?.trim()) row[field] = record[mapping[field]].trim()
    return row
  }) ?? []
  const payload: BatchInput = { project_id: projectId, name: name.trim() || filename, rows, defaults: { language, ...(voiceId ? { voice_id: voiceId } : {}), ...(modelId ? { model_id: modelId } : {}) } }
  const fingerprint = JSON.stringify(payload)
  useEffect(() => { setKey(createIdempotencyKey('tts')) }, [fingerprint])
  const preflight = useMutation({ mutationFn: ({ input }: { input: BatchInput; fingerprint: string }) => productionApi.analyzeBatch(input) })
  const validated = preflight.variables?.fingerprint === fingerprint ? preflight.data : undefined
  const submit = useMutation({ mutationFn: () => productionApi.createBatch({ ...payload, preflight_token: validated?.preflight_token }, key), onSuccess: (batch) => { setKey(createIdempotencyKey('tts')); void client.invalidateQueries({ queryKey: ['batches'] }); onCreated(batch.batch_id) } })
  async function importFile(file: File | undefined) {
    if (!file) return
    try {
      if (file.size > 5 * 1024 * 1024) throw new Error('Import files must be 5 MB or smaller.')
      const parsed = parseBatchImport(await file.text())
      setTable(parsed); setFilename(file.name); setName(file.name.replace(/\.[^.]+$/, '')); setImportError(null)
      setMapping(Object.fromEntries(mappingFields.map((field) => [field, parsed.columns.find((column) => column.toLowerCase() === field) ?? ''])) as Mapping)
      preflight.reset(); submit.reset(); setKey(createIdempotencyKey('tts'))
    } catch (error) { setImportError(error instanceof Error ? error : new Error('Unable to read file.')); setTable(null) }
  }
  return <section className={`${panel} space-y-4`} aria-label="Batch import"><div><h3 className="font-semibold">1. Import and map content</h3><p className="mt-1 text-sm text-slate-500">CSV with headers or a JSON array. Each row keeps its external ID through rendering and export.</p></div><div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4"><Field label="Project"><select className={control} value={projectId} onChange={(e) => setProjectId(e.target.value)}><option value="">Choose project</option>{projects.data?.items.map((project) => <option key={project.project_id} value={project.project_id}>{project.name}</option>)}</select></Field><Field label="Batch name"><input className={control} value={name} onChange={(e) => setName(e.target.value)} /></Field><Field label="CSV or JSON file"><input className={`${control} text-xs`} type="file" accept=".csv,.json,text/csv,application/json" onChange={(e) => { void importFile(e.target.files?.[0]); e.target.value = '' }} /></Field><div className="self-end"><Button variant="secondary" onClick={() => downloadFile(new Blob(['external_id,text,language\nwelcome,"Xin chào và chào mừng bạn.",vi\n'], { type: 'text/csv;charset=utf-8' }), 'batch-template.csv')}>Download template</Button></div></div>
    <Pager offset={projectOffset} total={projects.data?.total ?? 0} size={50} onChange={setProjectOffset} />
    <RequestError error={importError ?? projects.error ?? voices.error ?? models.error} />
    {table ? <><div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">{mappingFields.map((field) => <Field key={field} label={`Map ${field}`}><select className={control} value={mapping[field]} onChange={(e) => setMapping({ ...mapping, [field]: e.target.value })}><option value="">{field === 'text' ? 'Choose text column' : field === 'external_id' ? 'Generate row IDs' : 'Use default'}</option>{table.columns.map((column) => <option key={column} value={column}>{column}</option>)}</select></Field>)}</div><div className="grid gap-3 sm:grid-cols-3"><Field label="Default language"><select className={control} value={language} onChange={(e) => { setLanguage(e.target.value); setModelId('') }}><option value="vi">Vietnamese</option><option value="en">English</option></select></Field><Field label="Default voice"><select className={control} value={voiceId} onChange={(e) => setVoiceId(e.target.value)}><option value="">Use row voice</option>{voices.data?.map((voice) => <option key={voice.voice_id} value={voice.voice_id}>{voice.name} · {voice.language}</option>)}</select></Field><Field label="Default model"><select className={control} value={modelId} onChange={(e) => setModelId(e.target.value)}><option value="">Configured language default</option>{models.data?.models.filter((model) => model.languages.includes(language)).map((model) => <option key={model.model_id} value={model.model_id}>{model.label}{model.ready ? '' : ' · unavailable'}</option>)}</select></Field></div><p className="text-xs text-slate-500">{table.records.length} rows · {filename}. Mapped values override defaults. Validation runs on the server before any audio is generated.</p><Button variant="secondary" disabled={!projectId || !mapping.text || preflight.isPending || submit.isPending} onClick={() => preflight.mutate({ input: payload, fingerprint })}>{preflight.isPending ? 'Validating…' : '2. Validate rows'}</Button></> : null}
    <RequestError error={preflight.error ?? submit.error} />
    {preflight.data && !validated ? <p className="text-sm text-amber-800" role="status">Import settings changed. Validate again before submitting.</p> : null}
    {validated ? <div className="space-y-3 border-t border-slate-200 pt-4"><div className="flex flex-wrap justify-between gap-2"><h3 className="font-semibold">Validation report · {validated.row_count} rows</h3><Status value={validated.can_submit ? 'ready' : 'needs_changes'} /></div>{validated.errors.map((error, index) => <p key={index} role="alert" className="text-sm text-red-700">{error}</p>)}<div className="max-h-80 overflow-auto rounded border border-slate-200"><table className="w-full min-w-[600px] text-left text-xs"><thead className="sticky top-0 bg-slate-50"><tr>{['Row / source ID', 'Text after pronunciation', 'Voice / model', 'Validation'].map((heading) => <th key={heading} className="p-3">{heading}</th>)}</tr></thead><tbody>{validated.rows.map((row) => <tr key={row.row_number} className="border-t border-slate-100"><td className="p-3">{row.row_number}. {row.external_id}</td><td className="max-w-sm p-3">{row.normalized_text || row.text}</td><td className="p-3">{row.voice_id}<br />{row.model_id}</td><td className="p-3">{row.errors.length ? row.errors.map((error) => <p key={error} className="text-red-700">{error}</p>) : <span className="text-emerald-700">Valid</span>}{row.warnings.map((warning) => <p key={warning} className="text-amber-800">{warning}</p>)}</td></tr>)}</tbody></table></div><Button disabled={!validated.can_submit || submit.isPending} onClick={() => submit.mutate()}>{submit.isPending ? 'Creating batch…' : `3. Queue ${validated.row_count} rows`}</Button><p className="text-xs text-slate-500">Submission freezes the validated inputs. Results stay available in batch history.</p></div> : null}
  </section>
}

function BatchMonitor({ batch }: { batch: Batch }) {
  const { canWrite } = useProductionAccess()
  const client = useQueryClient()
  const [offset, setOffset] = useState(0)
  const [reviewItem, setReviewItem] = useState<BatchItem | null>(null)
  const [cancelOpen, setCancelOpen] = useState(false)
  const [retryIds, setRetryIds] = useState<string[]>([])
  const items = useQuery({ queryKey: ['batch-items', batch.batch_id, offset], queryFn: () => productionApi.batchItems(batch.batch_id, offset), refetchInterval: !finished.has(batch.status) ? 1500 : 8000 })
  const refresh = () => { void client.invalidateQueries({ queryKey: ['batch', batch.batch_id] }); void client.invalidateQueries({ queryKey: ['batch-items', batch.batch_id] }); void client.invalidateQueries({ queryKey: ['batches'] }) }
  const retry = useMutation({ mutationFn: () => productionApi.retryBatch(batch.batch_id, retryIds), onSuccess: () => { setRetryIds([]); refresh() } })
  const cancel = useMutation({ mutationFn: () => productionApi.cancelBatch(batch.batch_id), onSuccess: () => { setCancelOpen(false); refresh() } })
  const exportAudio = useMutation({ mutationFn: () => productionApi.exportBatch(batch.batch_id), onSuccess: (blob) => downloadFile(blob, `${batch.name || batch.batch_id}-approved.zip`) })
  const completed = (batch.counts.succeeded ?? 0) + (batch.counts.failed ?? 0) + (batch.counts.cancelled ?? 0)
  return <div className="space-y-4"><section className={`${panel} space-y-3`}><div className="flex flex-wrap items-start justify-between gap-2"><div><h2 className="text-lg font-semibold">{batch.name || 'Batch'}</h2><p className="mt-1 text-xs text-slate-500">{batch.batch_id}</p></div><Status value={batch.status} /></div><div aria-label="Batch progress" role="progressbar" aria-valuemin={0} aria-valuemax={batch.item_count} aria-valuenow={completed} className="h-2 overflow-hidden rounded-full bg-slate-100"><div className="h-full bg-blue-600 transition-all" style={{ width: `${batch.item_count ? Math.min(100, completed / batch.item_count * 100) : 0}%` }} /></div><p role="status" className="text-sm text-slate-600">{completed} of {batch.item_count} finished</p><div className="flex flex-wrap gap-2">{Object.entries(batch.counts).map(([status, count]) => <span key={status} className="rounded border border-slate-200 px-2 py-1 text-xs"><strong>{count}</strong> {status}</span>)}</div><div className="flex flex-wrap gap-2"><Button variant="secondary" disabled={!canWrite || !batch.counts.failed || retry.isPending} onClick={() => retry.mutate()}>{retry.isPending ? 'Queuing retry…' : retryIds.length ? `Retry ${retryIds.length} selected items` : 'Retry all failed items'}</Button><Button variant="secondary" disabled={!canWrite || finished.has(batch.status) || cancel.isPending} onClick={() => setCancelOpen(true)}>Cancel unfinished</Button><Button disabled={exportAudio.isPending} onClick={() => exportAudio.mutate()}><Download className="size-4" />{exportAudio.isPending ? 'Preparing…' : 'Export approved results'}</Button><Button variant="ghost" onClick={refresh} aria-label="Refresh batch"><RefreshCw className="size-4" /></Button></div><RequestError error={retry.error ?? cancel.error ?? exportAudio.error} onReload={refresh} /></section>
    <section className={panel}><h3 className="mb-3 font-semibold">Batch items</h3><RequestError error={items.error} onReload={() => { void items.refetch() }} />{items.isLoading ? <Loading /> : <div className="overflow-x-auto"><table className="w-full min-w-[620px] text-left text-sm"><thead className="bg-slate-50 text-xs text-slate-600"><tr>{['Source ID', 'Script / model', 'Processing', 'Review', ''].map((heading, index) => <th key={index} className="p-3">{heading}</th>)}</tr></thead><tbody>{items.data?.items.map((item) => <tr key={item.item_id} className="border-t border-slate-100"><td className="p-3 text-xs font-semibold">{item.status === 'failed' ? <label className="flex gap-2"><input type="checkbox" aria-label={`Retry ${item.external_id}`} checked={retryIds.includes(item.item_id)} onChange={(e) => setRetryIds((current) => e.target.checked ? [...current, item.item_id] : current.filter((id) => id !== item.item_id))} />{item.external_id}</label> : item.external_id}</td><td className="max-w-sm p-3"><p className="line-clamp-2">{item.text}</p><p className="mt-1 text-xs text-slate-500">{item.model_id}</p>{item.error ? <p className="mt-1 text-xs text-red-700">{item.error}</p> : null}</td><td className="p-3"><Status value={item.status} /></td><td className="p-3"><Status value={item.review_status || 'pending'} /></td><td className="p-3"><Button size="sm" variant="secondary" disabled={!item.take_id || item.status !== 'succeeded'} onClick={() => setReviewItem(item)}>Review audio</Button></td></tr>)}</tbody></table></div>}<Pager offset={offset} total={items.data?.total ?? 0} size={25} onChange={setOffset} /></section>
    {reviewItem ? <BatchReview key={reviewItem.take_id} projectId={batch.project_id} item={items.data?.items.find((item) => item.item_id === reviewItem.item_id) ?? reviewItem} onClose={() => setReviewItem(null)} onChanged={refresh} /> : null}
    <ConfirmDialog open={cancelOpen} error={cancel.error instanceof Error ? cancel.error.message : undefined} onOpenChange={setCancelOpen} title="Cancel unfinished batch items?" description="Completed audio remains available. Running inference stops at its next safe cancellation point." confirmLabel="Cancel unfinished" busy={cancel.isPending} busyLabel="Cancelling" onConfirm={() => cancel.mutate()} />
  </div>
}

function BatchReview({ projectId, item, onClose, onChanged }: { projectId: string; item: BatchItem; onClose: () => void; onChanged: () => void }) {
  return <section className={`${panel} space-y-3`} aria-label={`Review ${item.external_id}`}><div className="flex items-center justify-between gap-2"><h3 className="font-semibold">Review · {item.external_id}</h3><Button size="sm" variant="ghost" onClick={onClose}>Close review</Button></div><p className="text-sm text-slate-600">{item.text}</p><TakeReview projectId={projectId} take={item} onChanged={onChanged} /></section>
}
