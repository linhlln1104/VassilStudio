import { lazy } from 'react'

export const ProjectsRouteView = lazy(() => import('@/features/production/ProjectsView').then((module) => ({ default: module.ProjectsView })))
export const BatchesRouteView = lazy(() => import('@/features/production/BatchesView').then((module) => ({ default: module.BatchesView })))
export const ModelsRouteView = lazy(() => import('@/features/production/ModelsView').then((module) => ({ default: module.ModelsView })))
export const AdministrationRouteView = lazy(() => import('@/features/production/AdministrationView').then((module) => ({ default: module.AdministrationView })))

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
