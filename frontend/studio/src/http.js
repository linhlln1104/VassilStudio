export function createHttp(getApiKey) {
  function authFetch(url, options = {}) {
    const headers = new Headers(options.headers || {});
    const apiKey = getApiKey();
    if (apiKey) {
      headers.set("X-Vassil-API-Key", apiKey);
    }
    return fetch(url, { ...options, headers });
  }

  function withAuthQuery(url) {
    const apiKey = getApiKey();
    if (!apiKey) {
      return url;
    }

    const parsed = new URL(url, window.location.origin);
    parsed.searchParams.set("api_key", apiKey);
    return `${parsed.pathname}${parsed.search}${parsed.hash}`;
  }

  async function fetchJson(url, options = {}) {
    const response = await authFetch(url, options);
    await ensureOk(response);
    return response.json();
  }

  async function ensureOk(response) {
    if (response.ok) {
      return;
    }

    let message = `${response.status} ${response.statusText}`;
    try {
      const payload = await response.json();
      message = payload.message || payload.error || message;
    } catch {
      // Response was not JSON.
    }
    throw new Error(message);
  }

  return {
    authFetch,
    withAuthQuery,
    fetchJson,
    ensureOk,
  };
}
