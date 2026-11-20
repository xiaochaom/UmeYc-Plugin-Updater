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
export type State = { daily: boolean; last_checked: number; installed: Installed[]; watches: Watch[] };
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
export const takeNotifications = callable<[], { name: string; tag: string }[]>('take_notifications');
export const checkPlugin = localized<[string], State>('check_plugin');
export const watchPlugin = localized<[string, string], State>('watch');
export const unwatchPlugin = callable<[string], State>('unwatch');
export const startPhone = localized<[PhoneMode], { id: string; url: string }>('start_phone');
export const pollPhone = callable<[string], { status: 'waiting' | 'expired' } | { status: 'received'; url: string }>('poll_phone');
export const stopPhone = callable<[string]>('stop_phone');
export const prepareInstall = localized<[string], Candidate>('prepare_install');
export const prepareUpdate = localized<[string, string, string], Candidate>('prepare_update');

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

export const errorText = (error: unknown) => error instanceof Error ? error.message : String(error);
