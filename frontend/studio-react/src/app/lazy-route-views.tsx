import { lazy } from 'react'

export const GenerateRouteView = lazy(() =>
  import('@/features/generate/GenerateView').then((module) => ({ default: module.GenerateView })),
)

export const TranscribeRouteView = lazy(() =>
  import('@/features/transcribe/TranscribeView').then((module) => ({ default: module.TranscribeView })),
)

export const RealtimeRouteView = lazy(() =>
  import('@/features/realtime/RealtimeView').then((module) => ({ default: module.RealtimeView })),
)

export const VoicesRouteView = lazy(() =>
  import('@/features/voices/VoicesView').then((module) => ({ default: module.VoicesView })),
)

export const JobsRouteView = lazy(() =>
  import('@/features/jobs/JobsView').then((module) => ({ default: module.JobsView })),
)

export const SettingsRouteView = lazy(() =>
  import('@/features/settings/SettingsView').then((module) => ({ default: module.SettingsView })),
)
