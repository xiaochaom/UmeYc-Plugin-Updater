import { toaster } from '@decky/api';
import { takeNotifications } from './api';
import { copy } from './i18n';

export async function showUpdateNotifications() {
  if (typeof toaster?.toast !== 'function') return;
  try {
    const updates = await takeNotifications();
    for (const { name, tag } of updates) {
      toaster.toast({ title: copy().notificationTitle, body: `${name} · ${tag}`, showNewIndicator: true });
    }
  } catch (error) {
    console.warn('UmeYc-Plugin-Updater: could not show update notifications', error);
  }
}
