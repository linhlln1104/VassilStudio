import {
  AudioLines,
  Captions,
  History,
  Mic,
  Settings,
  UsersRound,
  Folders,
  Layers,
  Cpu,
  ShieldCheck,
  type LucideIcon,
} from 'lucide-react'
import type { ComponentType, LazyExoticComponent } from 'react'

import {
  GenerateRouteView,
  JobsRouteView,
  RealtimeRouteView,
  SettingsRouteView,
  TranscribeRouteView,
  VoicesRouteView,
  ProjectsRouteView,
  BatchesRouteView,
  ModelsRouteView,
  AdministrationRouteView,
} from './lazy-route-views'

export type RouteId = 'generate' | 'voices' | 'jobs' | 'transcribe' | 'realtime' | 'settings' | 'projects' | 'batches' | 'models' | 'administration'

export type StudioRoute = {
  id: RouteId
  label: string
  shortLabel: string
  icon: LucideIcon
  section: 'Production' | 'Create' | 'Manage' | 'System'
  component: ComponentType | LazyExoticComponent<ComponentType>
}

export const routes: StudioRoute[] = [
  { id: 'projects', label: 'Projects', shortLabel: 'Projects', icon: Folders, section: 'Production', component: ProjectsRouteView },
  { id: 'batches', label: 'Batches', shortLabel: 'Batches', icon: Layers, section: 'Production', component: BatchesRouteView },
  {
    id: 'generate',
    label: 'Generate',
    shortLabel: 'TTS',
    icon: AudioLines,
    section: 'Create',
    component: GenerateRouteView,
  },
  {
    id: 'transcribe',
    label: 'Transcribe',
    shortLabel: 'ASR',
    icon: Captions,
    section: 'Create',
    component: TranscribeRouteView,
  },
  {
    id: 'realtime',
    label: 'Realtime',
    shortLabel: 'Live',
    icon: Mic,
    section: 'Create',
    component: RealtimeRouteView,
  },
  {
    id: 'voices',
    label: 'Voices',
    shortLabel: 'Voices',
    icon: UsersRound,
    section: 'Manage',
    component: VoicesRouteView,
  },
  {
    id: 'jobs',
    label: 'Jobs',
    shortLabel: 'Jobs',
    icon: History,
    section: 'Manage',
    component: JobsRouteView,
  },
  {
    id: 'settings',
    label: 'Settings',
    shortLabel: 'Settings',
    icon: Settings,
    section: 'System',
    component: SettingsRouteView,
  },
  { id: 'models', label: 'Models', shortLabel: 'Models', icon: Cpu, section: 'System', component: ModelsRouteView },
  { id: 'administration', label: 'Administration', shortLabel: 'Admin', icon: ShieldCheck, section: 'System', component: AdministrationRouteView },
]

export function routeFromHash(hash: string): RouteId {
  const candidate = hash.replace(/^#\/?/, '').split('?')[0] as RouteId
  return routes.some((route) => route.id === candidate) ? candidate : 'generate'
}
