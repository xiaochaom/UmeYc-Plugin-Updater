export type Language = 'zh' | 'en';
export type LanguagePreference = Language | 'system';

const languageKey = 'UmeYc-Plugin-Updater.language';

export function getLanguagePreference(): LanguagePreference {
  const saved = window.localStorage.getItem(languageKey);
  return saved === 'zh' || saved === 'en' ? saved : 'system';
}

export function getLanguage(preference = getLanguagePreference()): Language {
  if (preference !== 'system') return preference;
  const locale = window.LocalizationManager?.m_rgLocalesToUse?.[0] || window.navigator.language;
  const primary = locale.toLowerCase().split(/[-_]/)[0];
  return ['zh', 'schinese', 'tchinese'].includes(primary) ? 'zh' : 'en';
}

export function saveLanguagePreference(preference: LanguagePreference) {
  if (preference === 'system') window.localStorage.removeItem(languageKey);
  else window.localStorage.setItem(languageKey, preference);
}

const zh = {
  locale: 'zh-CN', language: '界面语言 / Language', systemLanguage: '跟随系统', updates: '插件更新', daily: '每日检查',
  dailyOn: '已开启 · Decky 运行时每 24 小时检查，不自动安装', dailyOff: '已关闭 · 仍可手动检查',
  checkAll: '手动检查', working: '处理中…', addWatch: '添加监听插件', scanInstall: '扫码安装插件',
  lastChecked: '上次全量检查时间：', refresh: '刷新列表', watches: '监听列表', noWatches: '还没有监听的插件。',
  noAvailablePlugins: '没有未监听的已安装插件。',
  updateAvailable: '有可用更新', notificationTitle: '插件有可用更新', close: '关闭',
  qrHint: '用同一 Wi-Fi 下的手机扫码，在网页中粘贴地址。二维码 5 分钟内有效。',
  qrAlt: '手机扫码输入地址', qrLoading: '正在生成二维码…', qrExpired: '二维码已过期，请重新生成。',
  qrRegenerate: '重新生成', editWatch: '编辑监听插件', saving: '正在保存…', save: '保存',
  localPlugin: '本地插件', choosePlugin: '选择已安装插件', repoUrl: 'GitHub 仓库或 Releases 地址',
  repoExample: '例如 https://github.com/owner/repo', manualInput: '手动输入', scanRepo: '扫码输入 GitHub 地址',
  install: '安装', downloadZip: '下载并验证 ZIP', zipUrl: 'Decky ZIP 下载地址',
  zipExample: '例如 https://example.com/plugin.zip', scanZip: '扫码输入 ZIP 地址',
  replacePlugin: '这将替换本地同名插件。', downgradePlugin: '这将替换并降级本地同名插件。',
  pluginRoot: '该插件请求 root 权限。', trustedOnly: '插件会在 Deck 上运行代码。只安装你信任的来源；继续后由 Decky 确认。',
  changeUrl: '更换地址', missing: '未安装', unchecked: '尚未检查', error: '检查失败',
  unknown: '无法比较版本', current: '未发现较新版本', update: '有可用更新', no_asset: '有较新版本，但没有可用的 ZIP',
  releaseNetworkError: '无法读取 GitHub Release，请检查网络后重试',
  releaseTimeout: '连接 GitHub 超时，请检查网络或切换代理节点后重试',
  releaseTlsError: '与 GitHub 的 HTTPS 连接失败，请检查代理节点或 Deck 的日期和时间',
  releaseNotFound: '没有公开的正式 Release，或仓库不可用', releaseRateLimit: 'GitHub API 请求频率已达上限，请稍后重试',
  releaseHttpError: 'GitHub 查询失败', releaseTooLarge: 'Release 数据过大', releaseNoStable: '没有公开的正式 Release',
  multipleZips: '有多个 ZIP，无法确认对应成品', noZip: 'Release 没有上传 Decky ZIP 成品',
  confirmRemove: '确认移除', cancel: '取消', checking: '检查中…', checkUpdate: '检查更新',
  verifying: '下载并验证中…', continueUpdate: '继续更新', installUpdate: '更新',
  removeHint: '移除后将不再检查此插件的更新，不会卸载插件。', github: 'GitHub：', localVersion: '本地：',
  releaseVersion: 'Release：', versionUnknown: '未知', noNotes: '此版本未填写发布说明。', artifact: '成品：',
  updateRoot: '该版本请求 root 权限。请确认你信任这个来源。', editSource: '编辑来源', removeWatch: '移除监听',
  unsupportedLoader: '当前 Decky Loader 不支持此安装接口，请升级 Decky Loader 后重试。',
  downloadFailed: '下载或验证 ZIP 失败', installFailed: '无法打开 Decky 安装确认',
  unexpectedError: '操作失败，请重试。',
};

const en: Record<keyof typeof zh, string> = {
  locale: 'en', language: 'Language / 界面语言', systemLanguage: 'System default', updates: 'Plugin Updates', daily: 'Daily checks',
  dailyOn: 'On · Checks every 24 hours while Decky is running. Never installs automatically.', dailyOff: 'Off · You can still check manually.',
  checkAll: 'Check all', working: 'Working…', addWatch: 'Watch a plugin', scanInstall: 'Install via QR code',
  lastChecked: 'Last full check attempt: ', refresh: 'Refresh list', watches: 'Watched Plugins', noWatches: 'No plugins watched yet.',
  noAvailablePlugins: 'No unwatched plugins are installed.',
  updateAvailable: 'Update available', notificationTitle: 'Plugin update available', close: 'Close',
  qrHint: 'Scan with a phone on the same Wi-Fi network, then paste the URL. The QR code expires in 5 minutes.',
  qrAlt: 'Scan with your phone to enter a URL', qrLoading: 'Generating QR code…', qrExpired: 'The QR code has expired. Generate a new one.',
  qrRegenerate: 'Generate again', editWatch: 'Edit watched plugin', saving: 'Saving…', save: 'Save',
  localPlugin: 'Installed plugin', choosePlugin: 'Choose an installed plugin', repoUrl: 'GitHub repository or Releases URL',
  repoExample: 'Example: https://github.com/owner/repo', manualInput: 'Enter manually', scanRepo: 'Scan to enter a GitHub URL',
  install: 'Install', downloadZip: 'Download and verify ZIP', zipUrl: 'Decky ZIP download URL',
  zipExample: 'Example: https://example.com/plugin.zip', scanZip: 'Scan to enter a ZIP URL',
  replacePlugin: 'This replaces the installed plugin with the same name.', downgradePlugin: 'This replaces and downgrades the installed plugin with the same name.',
  pluginRoot: 'This plugin requests root access.', trustedOnly: 'Plugins run code on your Deck. Only install from sources you trust. Decky asks for confirmation before installing.',
  changeUrl: 'Change URL', missing: 'Not installed', unchecked: 'Not checked yet', error: 'Check failed',
  unknown: 'Cannot compare versions', current: 'No newer version found', update: 'Update available', no_asset: 'A newer version has no usable ZIP',
  releaseNetworkError: 'Could not read the GitHub release. Check your network and try again.',
  releaseTimeout: 'The GitHub connection timed out. Check your network or change proxy servers and try again.',
  releaseTlsError: 'The HTTPS connection to GitHub failed. Check your proxy server or the Deck’s date and time.',
  releaseNotFound: 'No public stable release found, or the repository is unavailable.', releaseRateLimit: 'GitHub API rate limit reached. Try again later.',
  releaseHttpError: 'GitHub request failed', releaseTooLarge: 'The release response is too large.', releaseNoStable: 'No public stable release found.',
  multipleZips: 'Multiple ZIP assets found; could not select one.', noZip: 'The release has no uploaded Decky ZIP.',
  confirmRemove: 'Confirm removal', cancel: 'Cancel', checking: 'Checking…', checkUpdate: 'Check for updates',
  verifying: 'Downloading and verifying…', continueUpdate: 'Continue update', installUpdate: 'Update',
  removeHint: 'Stops checking for updates to this plugin. It does not uninstall the plugin.', github: 'GitHub: ', localVersion: 'Installed: ',
  releaseVersion: 'Release: ', versionUnknown: 'Unknown', noNotes: 'No release notes provided.', artifact: 'Asset: ',
  updateRoot: 'This version requests root access. Make sure you trust the source.', editSource: 'Edit source', removeWatch: 'Stop watching',
  unsupportedLoader: 'This Decky Loader version does not support this install method. Update Decky Loader and try again.',
  downloadFailed: 'Could not download or verify the ZIP', installFailed: 'Could not open the Decky install prompt',
  unexpectedError: 'The operation failed. Try again.',
};

export function copy(language = getLanguage()) {
  return language === 'zh' ? zh : en;
}

export function checkSummary(succeeded: number, failed: number, updates: number, language: Language) {
  if (!succeeded && !failed) return copy(language).noWatches;
  if (language === 'zh') {
    if (!succeeded) return `检查失败 · ${failed} 个插件均未能读取 Release`;
    return `${failed ? '部分检查失败' : '检查完成'} · 成功 ${succeeded} · 失败 ${failed} · 可更新 ${updates}`;
  }
  if (!succeeded) return `Check failed · 0 succeeded · ${failed} failed`;
  return `${failed ? 'Some checks failed' : 'Check complete'} · ${succeeded} succeeded · ${failed} failed · ${updates} updatable`;
}

export function releaseError(code: string, httpStatus?: number, language = getLanguage()) {
  const text = copy(language);
  switch (code) {
    case 'releaseNetworkError': return text.releaseNetworkError;
    case 'releaseTimeout': return text.releaseTimeout;
    case 'releaseTlsError': return text.releaseTlsError;
    case 'releaseNotFound': return text.releaseNotFound;
    case 'releaseRateLimit': return text.releaseRateLimit;
    case 'releaseHttpError': return httpStatus ? `${text.releaseHttpError} (HTTP ${httpStatus})` : text.releaseHttpError;
    case 'releaseTooLarge': return text.releaseTooLarge;
    case 'releaseNoStable': return text.releaseNoStable;
    default: return language === 'zh' ? code : text.error;
  }
}

export function assetError(code: string) {
  const text = copy();
  return code === 'multipleZips' || code === '有多个 ZIP，无法确认对应成品' ? text.multipleZips : text.noZip;
}
