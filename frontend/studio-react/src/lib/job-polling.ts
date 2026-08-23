const ACTIVE_JOB_STATUSES = new Set(['queued', 'running', 'cancelling'])

const ACTIVE_POLL_INTERVAL_MS = 1_000
const IDLE_POLL_INTERVAL_MS = 8_000

type PollableJob = {
  status: string
}

export function jobRefetchInterval(jobs: readonly PollableJob[] | undefined) {
  return jobs?.some((job) => ACTIVE_JOB_STATUSES.has(job.status))
    ? ACTIVE_POLL_INTERVAL_MS
    : IDLE_POLL_INTERVAL_MS
}
