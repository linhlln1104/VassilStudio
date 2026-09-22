export function studioReturnTo(value: string | null | undefined, fallbackHash = ''): string {
  try {
    const url = new URL(value || '/studio', window.location.origin)
    if (url.origin !== window.location.origin || url.username || url.password ||
      !(url.pathname === '/studio' || url.pathname.startsWith('/studio/'))) {
      return '/studio'
    }
    if (!url.hash && /^#\/?(generate|voices|jobs|transcribe|realtime|settings)$/.test(fallbackHash)) {
      url.hash = fallbackHash
    }
    return `${url.pathname}${url.search}${url.hash}`
  } catch {
    return '/studio'
  }
}

export function authReturnTo(): string {
  return studioReturnTo(new URLSearchParams(window.location.search).get('return_to'), window.location.hash)
}

export function authPageUrl(page: 'login' | 'setup', destination?: string): string {
  const returnTo = destination ?? studioReturnTo(
    `${window.location.pathname}${window.location.search}${window.location.hash}`,
  )
  return `/${page}?${new URLSearchParams({ return_to: studioReturnTo(returnTo) })}`
}
