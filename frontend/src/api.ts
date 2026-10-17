import { UserManager, WebStorageStateStore, type User } from 'oidc-client-ts';
import type { Config } from './types';

let manager: UserManager | null = null;
let refreshing: Promise<User | null> | null = null;
export const AUTH_EXPIRED_EVENT = 'clearance-gap-auth-expired';

async function expireLogin() {
  await manager?.removeUser();
  sessionStorage.removeItem('clearance-gap-session');
  window.dispatchEvent(new Event(AUTH_EXPIRED_EVENT));
}

export async function configureAuth(config: Config) {
  if (config.authMode !== 'cognito') { manager = null; return; }
  const domain = config.domain.replace(/\/$/, '');
  const scope = ['openid', 'profile', 'email', config.requiredScope].filter(Boolean).join(' ');
  manager = new UserManager({ authority: config.issuer!, client_id: config.clientId,
    redirect_uri: `${location.origin}/auth/callback`, post_logout_redirect_uri: location.origin,
    response_type: 'code', scope, disablePKCE: false, loadUserInfo: false,
    // Renew with the refresh token during API use; Cognito does not support prompt=none iframe renewal.
    automaticSilentRenew: false,
    stateStore: new WebStorageStateStore({ store: sessionStorage }),
    userStore: new WebStorageStateStore({ store: sessionStorage }),
    metadata: { issuer: config.issuer!, authorization_endpoint: `${domain}/oauth2/authorize`,
      token_endpoint: `${domain}/oauth2/token`, revocation_endpoint: `${domain}/oauth2/revoke` } });
  await manager.clearStaleState();
  if (location.pathname === '/auth/callback') {
    try { await manager.signinRedirectCallback(); }
    finally { history.replaceState({}, '', '/live'); }
  }
}
export async function signIn() { await manager?.signinRedirect(); }
export async function signOut(config: Config) {
  try { await manager?.revokeTokens(['refresh_token']); }
  finally {
    await expireLogin();
    if (config.authMode === 'cognito') location.assign(`${config.domain.replace(/\/$/, '')}/logout?client_id=${encodeURIComponent(config.clientId)}&logout_uri=${encodeURIComponent(location.origin)}`);
  }
}
export async function api<T>(path: string, body?: unknown, requestId?: string): Promise<T> {
  const headers: Record<string, string> = {};
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  if (requestId) headers['Idempotency-Key'] = requestId;
  if (manager) {
    let user = await manager.getUser();
    if (!user) throw new Error('Sign in to continue.');
    if ((user.expires_in ?? 0) < 60) {
      try {
        if (!user.refresh_token) throw new Error('No refresh token');
        refreshing ??= manager.signinSilent().finally(() => { refreshing = null; });
        user = await refreshing;
        if (!user || user.expired) throw new Error('Expired access token');
      } catch {
        await expireLogin();
        throw new Error('Your sign-in has expired. Sign in again to continue.');
      }
    }
    headers.Authorization = `Bearer ${user.access_token}`;
  }
  const response = await fetch(`/api${path}`, { method: body !== undefined ? 'POST' : 'GET', headers,
    cache: 'no-store',
    body: body !== undefined ? JSON.stringify(body) : undefined });
  if (!response.ok) {
    if (response.status === 401 && manager) await expireLogin();
    const data = await response.json().catch(() => ({}));
    throw new Error(typeof data.detail === 'string' ? data.detail : `Request failed (${response.status})`);
  }
  return response.json();
}
