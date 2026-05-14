export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly body: unknown,
    message: string
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

function resolveOrigin(): string {
  if (typeof window !== 'undefined' && window.location?.origin) {
    return window.location.origin;
  }

  const explicitOrigin =
    process.env.NEXT_PUBLIC_SITE_URL ??
    process.env.SITE_URL ??
    process.env.APP_URL;
  if (explicitOrigin) return explicitOrigin.replace(/\/$/, '');

  const vercelUrl = process.env.VERCEL_URL;
  if (vercelUrl) {
    return vercelUrl.startsWith('http') ? vercelUrl.replace(/\/$/, '') : `https://${vercelUrl.replace(/\/$/, '')}`;
  }

  return 'http://localhost:3000';
}

function resolveBaseUrl(baseUrl: string): string {
  if (/^https?:\/\//i.test(baseUrl)) {
    return baseUrl.replace(/\/$/, '');
  }
  if (baseUrl.startsWith('/')) {
    return `${resolveOrigin()}${baseUrl}`.replace(/\/$/, '');
  }
  return `${resolveOrigin()}/${baseUrl}`.replace(/\/$/, '');
}

// Encode each path segment individually (Devanagari-safe).
// Input: "/v1/keywords/आत्मा" → encodes each slash-separated segment
// Query strings (after ?) are passed through unchanged.
function encodePath(path: string): string {
  const qIdx = path.indexOf('?');
  const pathPart = qIdx === -1 ? path : path.slice(0, qIdx);
  const queryPart = qIdx === -1 ? '' : path.slice(qIdx);
  const encodedPath = pathPart
    .split('/')
    .map((seg) => (seg === '' ? '' : encodeURIComponent(seg)))
    .join('/');
  return encodedPath + queryPart;
}

export async function apiFetch<T>(
  baseUrl: string,
  path: string,
  init?: RequestInit
): Promise<T> {
  const url = resolveBaseUrl(baseUrl) + encodePath(path);
  const res = await fetch(url, init);
  if (!res.ok) {
    let body: unknown;
    try { body = await res.json(); } catch { body = null; }
    throw new ApiError(res.status, body, `API ${res.status}: ${path}`);
  }
  return res.json() as Promise<T>;
}
