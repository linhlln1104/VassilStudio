import type { JobProgressStage, JobStatus } from '@/lib/api'


type RuntimeJob = {
  status: JobStatus
  progress_stage?: JobProgressStage
  progressStage?: JobProgressStage
}

export function resolvedProgressStage(job: RuntimeJob): JobProgressStage {
  const stage = job.progress_stage ?? job.progressStage
  if (stage) {
    return stage
  }
  if (job.status === 'running' || job.status === 'cancelling') {
    return 'running_model'
  }
  return job.status
}

export function jobProgressLabel(job: RuntimeJob, type: 'TTS' | 'ASR'): string {
  const stage = resolvedProgressStage(job)
  const labels: Record<JobProgressStage, string> = {
    queued: 'Waiting in queue',
    preparing_input: type === 'TTS' ? 'Preparing voice reference' : 'Preparing audio',
    running_model: type === 'TTS' ? 'Synthesizing audio' : 'Transcribing audio',
    finalizing: type === 'TTS' ? 'Writing output' : 'Finalizing transcript',
    retry_wait: 'Waiting to retry',
    succeeded: 'Completed',
    failed: 'Failed',
    cancelled: 'Cancelled',
  }
  return labels[stage]
}

export function jobStatusLabel(status: JobStatus): string {
  if (status === 'cancelling') return 'Stopping'
  if (status === 'succeeded') return 'Succeeded'
  return status.charAt(0).toUpperCase() + status.slice(1)
}

export function cancellationResultMessage(
  job: RuntimeJob & { job_id: string },
  compactJobId: string,
  type: 'TTS' | 'ASR',
): string {
  if (job.status === 'cancelled') {
    return `${compactJobId} was removed before processing started.`
  }

  const stage = jobProgressLabel(job, type).toLowerCase()
  return `${compactJobId} is stopping at the next safe point after ${stage}.`
}
