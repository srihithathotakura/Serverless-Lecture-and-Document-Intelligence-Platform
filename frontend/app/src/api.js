import { getIdToken } from './auth.js';

export async function api(path, opts = {}) {
  let res;

  try {
    const token = await getIdToken();

    res = await fetch(window.APP_CONFIG.apiUrl + path, {
      ...opts,
      headers: {
        Authorization: 'Bearer ' + token,
        'Content-Type': 'application/json',
        ...(opts.headers || {}),
      },
    });
  } catch (e) {
    if (e instanceof TypeError) {
      throw new Error('Network error. Check your connection and try again.');
    }
    throw e;
  }

  const data = await res.json().catch(() => ({}));

  if (!res.ok) {
    throw new Error(
      data.error ||
        (res.status === 401
          ? 'Session expired. Please sign in again.'
          : res.statusText),
    );
  }

  return data;
}
