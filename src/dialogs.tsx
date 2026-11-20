import { DialogButton, DropdownItem, Focusable, ModalRoot, TextField } from '@decky/ui';
import type { ModalRootProps } from '@decky/ui';
import type { ReactNode } from 'react';
import { useEffect, useState } from 'react';
import qrcode from 'qrcode-generator';
import {
  checkPlugin, errorText, pollPhone, prepareInstall, prepareUpdate, requestInstall, startPhone, stopPhone, unwatchPlugin, watchPlugin,
} from './api';
import type { Candidate, PhoneMode, State, Watch } from './api';
import { assetError, copy, releaseError } from './i18n';
import { showUpdateNotifications } from './notifications';

const layout = { display: 'flex', gap: 10, marginTop: 12 };

function Dialog({ title, children, closeModal, busy, actions }: ModalRootProps & {
  title: string; busy?: boolean; actions?: ReactNode;
}) {
  const close = () => { if (!busy) closeModal?.(); };
  return (
    <ModalRoot bDisableBackgroundDismiss={busy} bHideCloseIcon={busy} onCancel={close} onEscKeypress={close}>
      <Focusable flow-children="column" style={{ width: 'min(500px, 78vw)', padding: 16 }}>
        <h2 style={{ margin: '0 0 12px' }}>{title}</h2>
        {children}
        <Focusable flow-children="row" style={layout}>
          {actions}
          <DialogButton disabled={busy} onClick={close}>{copy().close}</DialogButton>
        </Focusable>
      </Focusable>
    </ModalRoot>
  );
}

function PhoneInput({ mode, receive }: { mode: PhoneMode; receive: (url: string) => void }) {
  const text = copy();
  const [qr, setQr] = useState('');
  const [error, setError] = useState('');
  const [attempt, retry] = useState(0);
  useEffect(() => {
    let disposed = false;
    let id = '';
    let timer: ReturnType<typeof setTimeout>;
    const stop = () => { if (id) void stopPhone(id).catch(() => undefined); };
    const report = (cause: unknown) => {
      if (!disposed) {
        setQr('');
        setError(errorText(cause));
      }
      stop();
    };
    const poll = async () => {
      try {
        const result = await pollPhone(id);
        if (disposed) return;
        if (result.status === 'received') {
          stop();
          receive(result.url);
        } else if (result.status === 'expired') {
          report(text.qrExpired);
        } else {
          timer = setTimeout(() => void poll(), 1000);
        }
      } catch (cause) { report(cause); }
    };
    setQr('');
    setError('');
    void startPhone(mode).then((session) => {
      id = session.id;
      if (disposed) return stop();
      const code = qrcode(0, 'M');
      code.addData(session.url);
      code.make();
      setQr(code.createDataURL(5, 20));
      void poll();
    }).catch(report);
    return () => {
      disposed = true;
      clearTimeout(timer);
      stop();
    };
  }, [mode, receive, attempt, text]);

  return (
    <div style={{ textAlign: 'center' }}>
      <p>{text.qrHint}</p>
      {qr && <img width={168} height={168} src={qr} alt={text.qrAlt} style={{ imageRendering: 'pixelated' }} />}
      {!qr && !error && <p role="status">{text.qrLoading}</p>}
      {error && <p role="alert">{error}</p>}
      {error && <DialogButton onClick={() => retry(attempt + 1)}>{text.qrRegenerate}</DialogButton>}
    </div>
  );
}

export function WatchDialog({ installed, existing, closeModal, onSave }: ModalRootProps & {
  installed: State['installed']; existing?: Watch; onSave: () => void;
}) {
  const text = copy();
  const [name, setName] = useState(existing?.name ?? '');
  const [url, setUrl] = useState(existing ? `https://github.com/${existing.repo}` : '');
  const [scan, setScan] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [receive] = useState(() => (value: string) => { setUrl(value); setScan(false); });
  const save = async () => {
    setBusy(true);
    setError('');
    try {
      await watchPlugin(name, url);
      closeModal?.();
      onSave();
    } catch (cause) {
      setError(errorText(cause));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Dialog title={existing ? text.editWatch : text.addWatch} closeModal={closeModal} busy={busy} actions={
      <DialogButton disabled={!name || !url.trim() || busy || scan} onClick={() => void save()}>
        {busy ? text.saving : text.save}
      </DialogButton>
    }>
      <DropdownItem label={text.localPlugin} strDefaultLabel={text.choosePlugin} selectedOption={name}
        disabled={Boolean(existing) || busy || scan} rgOptions={installed.map((plugin) => ({ label: plugin.name, data: plugin.name }))}
        onChange={({ data }) => {
          setName(data);
          setUrl(installed.find((plugin) => plugin.name === data)?.repository ?? '');
          setError('');
        }} />
      <TextField label={text.repoUrl} description={text.repoExample}
        value={url} disabled={!name || busy || scan} onChange={(event) => setUrl(event.currentTarget.value)} />
      <DialogButton disabled={!name || busy} onClick={() => setScan(!scan)}>
        {scan ? text.manualInput : text.scanRepo}
      </DialogButton>
      {scan && <PhoneInput mode="repository" receive={receive} />}
      {error && <p role="alert">{error}</p>}
    </Dialog>
  );
}

export function InstallDialog({ closeModal }: ModalRootProps) {
  const text = copy();
  const [url, setUrl] = useState('');
  const [scan, setScan] = useState(true);
  const [candidate, setCandidate] = useState<Candidate>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [receive] = useState(() => (value: string) => { setUrl(value); setScan(false); });
  const proceed = async () => {
    setBusy(true);
    setError('');
    try {
      if (candidate) {
        await requestInstall(candidate);
        closeModal?.();
      } else {
        setCandidate(await prepareInstall(url));
      }
    } catch (cause) {
      setError(errorText(cause));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Dialog title={text.scanInstall} closeModal={closeModal} busy={busy} actions={
      <DialogButton disabled={!url.trim() || busy || scan} onClick={() => void proceed()}>
        {busy ? text.working : candidate ? text.install : text.downloadZip}
      </DialogButton>
    }>
      {!candidate && <TextField label={text.zipUrl} description={text.zipExample}
        value={url} disabled={busy || scan} onChange={(event) => setUrl(event.currentTarget.value)} />}
      {!candidate && <DialogButton disabled={busy} onClick={() => setScan(!scan)}>
        {scan ? text.manualInput : text.scanZip}
      </DialogButton>}
      {scan && <PhoneInput mode="zip" receive={receive} />}
      {candidate && <>
        <p>{candidate.name} · {candidate.version}</p>
        {candidate.kind !== 0 && <p>{candidate.kind === 3 ? text.downgradePlugin : text.replacePlugin}</p>}
        {candidate.root && <p role="alert">{text.pluginRoot}</p>}
        <p>{text.trustedOnly}</p>
        <DialogButton disabled={busy} onClick={() => setCandidate(undefined)}>{text.changeUrl}</DialogButton>
      </>}
      {error && <p role="alert">{error}</p>}
    </Dialog>
  );
}

export function WatchDetailsDialog({ initialItem, onChange, onEdit, closeModal }: ModalRootProps & {
  initialItem: Watch; onChange: (state: State) => void; onEdit: () => void;
}) {
  const text = copy();
  const [item, setItem] = useState(initialItem);
  const [operation, setOperation] = useState<'check' | 'update' | 'remove'>();
  const [confirmRemove, setConfirmRemove] = useState(false);
  const [error, setError] = useState('');
  const [privileged, setPrivileged] = useState<Candidate>();
  const busy = Boolean(operation);
  const release = item.release && !('error' in item.release) ? item.release : null;
  const canUpdate = item.status === 'update' && Boolean(release?.asset);
  const run = async (kind: NonNullable<typeof operation>, action: () => Promise<void>) => {
    setOperation(kind);
    setError('');
    try {
      await action();
    } catch (cause) {
      setError(errorText(cause));
    } finally {
      setOperation(undefined);
    }
  };
  const checkUpdate = () => run('check', async () => {
    setPrivileged(undefined);
    const state = await checkPlugin(item.name);
    void showUpdateNotifications();
    onChange(state);
    const checked = state.watches.find((watch) => watch.name === item.name);
    if (checked) setItem(checked);
    else closeModal?.();
  });
  const update = () => run('update', async () => {
    if (!canUpdate || !release?.asset) return;
    const candidate = privileged ?? await prepareUpdate(item.name, release.tag, release.asset.url);
    if (candidate.root && !privileged) {
      setPrivileged(candidate);
    } else {
      await requestInstall(candidate);
      closeModal?.();
    }
  });
  const remove = () => run('remove', async () => {
    onChange(await unwatchPlugin(item.name));
    closeModal?.();
  });

  return (
    <Dialog title={item.name} closeModal={closeModal} busy={busy} actions={confirmRemove ? <>
      <DialogButton disabled={busy} onClick={() => void remove()}>{text.confirmRemove}</DialogButton>
      <DialogButton disabled={busy} onClick={() => { setConfirmRemove(false); setError(''); }}>{text.cancel}</DialogButton>
    </> : <>
      <DialogButton disabled={busy} onClick={() => void checkUpdate()}>
        {operation === 'check' ? text.checking : text.checkUpdate}
      </DialogButton>
      {canUpdate && <DialogButton disabled={busy} onClick={() => void update()}>
        {operation === 'update' ? text.verifying : privileged ? text.continueUpdate : text.installUpdate}
      </DialogButton>}
    </>}>
      {confirmRemove ? <p>{text.removeHint}</p> : <>
        <div style={{ overflowWrap: 'anywhere' }}>{text.github}{item.repo}</div>
        <div>{text.localVersion}{item.version === null ? text.missing : item.version || text.versionUnknown}
          {release && ` · ${text.releaseVersion}${release.tag}`}</div>
        <div role="status">{item.release && 'error' in item.release ? releaseError(item.release.error, item.release.http_status) : text[item.status]}</div>
        {release && ['update', 'no_asset', 'unknown'].includes(item.status) && <>
          <p>{release.title}{release.published_at ? ` · ${new Date(release.published_at).toLocaleDateString(text.locale)}` : ''}</p>
          <Focusable tabIndex={0} style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', maxHeight: '22vh', overflowY: 'auto' }}>
            {release.notes.trim() || text.noNotes}
          </Focusable>
          <p style={{ overflowWrap: 'anywhere' }}>{release.asset ? `${text.artifact}${release.asset.name}` : assetError(release.asset_error)}</p>
        </>}
        {privileged && <p role="alert">{text.updateRoot}</p>}
        <Focusable flow-children="row" style={layout}>
          {item.version !== null && <DialogButton disabled={busy} onClick={() => { closeModal?.(); onEdit(); }}>{text.editSource}</DialogButton>}
          <DialogButton disabled={busy} onClick={() => { setConfirmRemove(true); setError(''); }}>{text.removeWatch}</DialogButton>
        </Focusable>
      </>}
      {error && <p role="alert">{error}</p>}
    </Dialog>
  );
}
