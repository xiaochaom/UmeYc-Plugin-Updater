import { addEventListener, definePlugin, removeEventListener, useQuickAccessVisible } from '@decky/api';
import { ButtonItem, DialogButton, DropdownItem, PanelSection, PanelSectionRow, quickAccessMenuClasses, showModal, ToggleField } from '@decky/ui';
import { useCallback, useEffect, useState } from 'react';
import { check, errorText, getState, setDaily, signOutGitHub } from './api';
import type { State } from './api';
import { GitHubLoginDialog, InstallDialog, WatchDetailsDialog, WatchDialog } from './dialogs';
import { checkProgress, checkSummary, copy, getLanguage, getLanguagePreference, releaseError, saveLanguagePreference } from './i18n';
import { showUpdateNotifications } from './notifications';

const pluginName = 'UmeYc-Plugin-Updater';
type CheckResult = { watches: State['watches']; partial: boolean } | { error: string };

function Home() {
  const [state, setState] = useState<State>();
  const [language, setLanguage] = useState(getLanguagePreference);
  const [operation, setOperation] = useState<'check' | 'settings'>();
  const [error, setError] = useState('');
  const [checkResult, setCheckResult] = useState<CheckResult>();
  const busy = Boolean(operation);
  const visible = useQuickAccessVisible?.() ?? true;
  const locale = getLanguage(language);
  const text = copy(locale);
  const refresh = useCallback(() => {
    void getState().then(setState, (cause) => setError(errorText(cause)));
  }, []);
  useEffect(() => {
    if (!visible) return;
    refresh();
    addEventListener('updates_changed', refresh);
    const backend = window.DeckyBackend;
    backend?.addEventListener?.('loader/plugin_download_finish', refresh);
    return () => {
      removeEventListener('updates_changed', refresh);
      backend?.removeEventListener?.('loader/plugin_download_finish', refresh);
    };
  }, [visible, refresh]);

  const run = async (kind: NonNullable<typeof operation>, action: () => Promise<State>) => {
    setOperation(kind);
    setError('');
    if (kind === 'check') setCheckResult(undefined);
    try {
      const result = await action();
      setState(result);
      if (kind === 'check') {
        const checked = new Set(result.checked_names);
        setCheckResult({ watches: result.watches.filter(({ name }) => checked.has(name)), partial: result.check_pending > 0 });
      }
    } catch (cause) {
      if (kind === 'check') setCheckResult({ error: errorText(cause) });
      else setError(errorText(cause));
    } finally {
      setOperation(undefined);
    }
  };
  const watchedNames = new Set(state?.watches.map(({ name }) => name));
  const available = state?.installed.filter(({ name }) => !watchedNames.has(name)) ?? [];
  const addWatch = () => {
    if (available.length) showModal(<WatchDialog installed={available} onSave={refresh} />);
  };
  const editSource = (item: State['watches'][number]) => {
    const installed = state?.installed.filter(({ name }) => name === item.name) ?? [];
    if (installed.length) showModal(<WatchDialog installed={installed} existing={item} onSave={refresh} />);
  };
  const checkAll = async () => {
    const checked = await check();
    void showUpdateNotifications();
    return checked;
  };
  const github = state?.github;
  const manageGitHub = () => {
    if (github?.connected) {
      void run('settings', async () => {
        if ((await signOutGitHub()).status !== 'signed_out') throw new Error(text.unexpectedError);
        return getState();
      });
    } else if (github?.available) {
      showModal(<GitHubLoginDialog onChange={refresh} />);
    }
  };
  const checkedWatches = checkResult && 'watches' in checkResult ? checkResult.watches : [];
  const failureReasons = checkedWatches.flatMap(({ release }) =>
    release && 'error' in release ? [releaseError(release.error, release.http_status, locale)] : []);
  const succeeded = checkedWatches.filter(({ release }) => release && !('error' in release)).length;
  const updates = checkedWatches.filter(({ status }) => status === 'update').length;
  const failure = Boolean(checkResult && 'error' in checkResult) || failureReasons.length > 0;
  const feedback = operation === 'check' ? text.checking
    : checkResult && ('error' in checkResult ? `${text.error} · ${checkResult.error}`
      : checkResult.partial && !checkedWatches.length ? undefined
      : checkSummary(succeeded, failureReasons.length, updates, locale, checkResult.partial));
  const progress = state && (state.check_pending > 0 || state.check_retry_at > 0)
    ? checkProgress(state.check_pending, state.check_retry_at, state.check_auto_resume, locale) : undefined;
  return <>
    <PanelSection title={text.updates}>
      <PanelSectionRow><ToggleField label={text.daily} checked={state?.daily ?? false} disabled={!state || busy}
        description={state?.daily ? text.dailyOn : text.dailyOff}
        onChange={(enabled) => void run('settings', () => setDaily(enabled))} /></PanelSectionRow>
      <PanelSectionRow><ButtonItem layout="below" disabled={!state?.watches.length || busy}
        onClick={() => void run('check', checkAll)}>{operation === 'check' ? text.checking : text.checkAll}</ButtonItem></PanelSectionRow>
      {feedback && <PanelSectionRow>
        <div role={failure ? 'alert' : 'status'} style={{ color: failure ? '#ffb4b4' : undefined, overflowWrap: 'anywhere' }}>
          <div>{feedback}</div>
          {[...new Set(failureReasons)].map((reason) => <div key={reason}>{reason}</div>)}
        </div>
      </PanelSectionRow>}
      {progress && <PanelSectionRow><div role="status">{progress}</div></PanelSectionRow>}
      {github && <PanelSectionRow><ButtonItem layout="below" disabled={busy || (!github.available && !github.connected)}
        description={github.connected ? text.githubSignedIn : github.available ? text.githubAnonymous : text.githubLoginUnavailable}
        onClick={manageGitHub}>{github.connected ? text.githubSignOut : text.githubSignIn}</ButtonItem></PanelSectionRow>}
      <PanelSectionRow><ButtonItem layout="below" disabled={!available.length || busy}
        description={state && !available.length ? text.noAvailablePlugins : undefined}
        onClick={addWatch}>{text.addWatch}</ButtonItem></PanelSectionRow>
      <PanelSectionRow><ButtonItem layout="below" onClick={() => showModal(<InstallDialog />)}>{text.scanInstall}</ButtonItem></PanelSectionRow>
      <PanelSectionRow><DropdownItem label={text.language} selectedOption={language} disabled={busy}
        rgOptions={[{ label: text.systemLanguage, data: 'system' }, { label: '简体中文', data: 'zh' }, { label: 'English', data: 'en' }]}
        onChange={({ data }) => { saveLanguagePreference(data); setLanguage(data); setError(''); }} /></PanelSectionRow>
      {Boolean(state?.last_checked) && <PanelSectionRow>
        <div>{text.lastChecked}{new Date(state!.last_checked * 1000).toLocaleString(text.locale)}</div>
      </PanelSectionRow>}
      {error && <PanelSectionRow><p role="alert">{error}</p><ButtonItem layout="below" onClick={refresh}>{text.refresh}</ButtonItem></PanelSectionRow>}
    </PanelSection>
    <PanelSection title={text.watches}>
      {state?.watches.length === 0 && <PanelSectionRow><div>{text.noWatches}</div></PanelSectionRow>}
      {state?.watches.map((item) => <PanelSectionRow key={item.name}>
        <DialogButton disabled={busy} aria-label={item.status === 'update' ? `${item.name} · ${text.updateAvailable}` : item.name}
          style={{ width: '100%', minWidth: 0, position: 'relative', textAlign: 'left', paddingRight: 22, marginBottom: 8 }}
          onClick={() => showModal(<WatchDetailsDialog initialItem={item} onChange={setState} onEdit={() => editSource(item)} />)}>
          <span style={{ display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.name}</span>
          {item.status === 'update' && <span aria-hidden="true" style={{
            position: 'absolute', top: 8, right: 8, width: 8, height: 8, borderRadius: '50%', background: '#69d77c',
          }} />}
        </DialogButton>
      </PanelSectionRow>)}
    </PanelSection>
  </>;
}

export default definePlugin(() => {
  addEventListener('updates_changed', showUpdateNotifications);
  void showUpdateNotifications();
  return {
    name: pluginName,
    titleView: <div className={quickAccessMenuClasses.Title}>{pluginName}</div>,
    icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <path d="M12 3v12m-5-5 5 5 5-5M4 17v4h16v-4" />
    </svg>,
    content: <Home />,
    onDismount: () => removeEventListener('updates_changed', showUpdateNotifications),
  };
});
