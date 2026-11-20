import { callable } from '@decky/api';
import { copy, getLanguage } from './i18n';
import type { Language } from './i18n';

export type Installed = { name: string; folder: string; version: string; repository: string | null };
export type Release = {
  title: string;
  tag: string;
  notes: string;
  published_at: string | null;
  asset: { name: string; url: string; digest?: string } | null;
  asset_error: string;
};
export type Watch = {
  name: string;
  repo: string;
  version: string | null;
  status: 'missing' | 'unchecked' | 'error' | 'unknown' | 'current' | 'update' | 'no_asset';
  release: Release | { error: string; http_status?: number } | null;
};
export type State = {
  daily: boolean; last_checked: number; installed: Installed[]; watches: Watch[];
  github: { available: boolean; connected: boolean };
  check_pending: number; check_retry_at: number; check_auto_resume: boolean; checked_names?: string[];
};
type GitHubLoginEnd = { status: 'connected' | 'unavailable' | 'device_flow_disabled' | 'expired' | 'denied' | 'error' };
type GitHubLoginWaiting = { status: 'waiting'; retry_in: number };
export type PhoneMode = 'repository' | 'zip';
export type Candidate = {
  name: string; version: string; folder: string; root: boolean; artifact: string; sha256: string; kind: number;
};

declare global {
  interface Window {
    DeckyBackend?: {
      call(route: 'utilities/install_plugin', artifact: string, name: string, version: string,
        hash: string, installType: number): Promise<void>;
      addEventListener(event: string, listener: () => void): void;
      removeEventListener(event: string, listener: () => void): void;
    };
  }
}

export const getState = callable<[], State>('state');
export const setDaily = callable<[boolean], State>('set_daily');
export const check = callable<[], State>('check');
export const startGitHubLogin = callable<[], GitHubLoginEnd | (GitHubLoginWaiting & {
  id: string; code: string; url: string;
})>('start_github_login');
export const pollGitHubLogin = callable<[string], GitHubLoginEnd | GitHubLoginWaiting>('poll_github_login');
export const cancelGitHubLogin = callable<[string]>('cancel_github_login');
export const signOutGitHub = callable<[], { status: 'signed_out' | 'error' }>('sign_out_github');
export const takeNotifications = callable<[], { name: string; tag: string }[]>('take_notifications');
export const checkPlugin = localized<[string], State>('check_plugin');
export const watchPlugin = localized<[string, string], State>('watch');
export const unwatchPlugin = callable<[string], State>('unwatch');
export const startPhone = localized<[PhoneMode], { id: string; url: string }>('start_phone');
export const pollPhone = callable<[string], { status: 'waiting' | 'expired' } | { status: 'received'; url: string }>('poll_phone');
export const stopPhone = callable<[string]>('stop_phone');
export const prepareInstall = prepareCandidate<[string]>('prepare_install');
export const prepareUpdate = prepareCandidate<[string, string, string]>('prepare_update');

function prepareCandidate<Args extends unknown[]>(method: string) {
  const invoke = localized<Args, { candidate: Candidate } | { error: string }>(method);
  return async (...args: Args) => {
    const result = await invoke(...args);
    if ('error' in result) throw new Error(result.error);
    return result.candidate;
  };
}

function localized<Args extends unknown[], Result>(method: string) {
  const invoke = callable<[...Args, Language], Result>(method);
  return (...args: Args) => invoke(...args, getLanguage());
}

export async function requestInstall(candidate: Candidate) {
  const backend = window.DeckyBackend;
  if (typeof backend?.call !== 'function') {
    throw new Error(copy().unsupportedLoader);
  }
  await backend.call('utilities/install_plugin', candidate.artifact, candidate.name,
    candidate.version, candidate.sha256, candidate.kind);
}

export function errorText(error: unknown) {
  const detail = error && typeof error === 'object' && 'message' in error ? error.message : error;
  return typeof detail === 'string' && detail.trim() ? detail : copy().unexpectedError;
}
