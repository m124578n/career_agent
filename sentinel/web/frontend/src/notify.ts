// 瀏覽器桌面通知薄封裝。未授權/不支援 → 靜默 no-op（fallback 靠儀表板橫幅）。
export async function ensurePermission(): Promise<void> {
  if (!("Notification" in window)) return;
  if (Notification.permission === "default") {
    try {
      await Notification.requestPermission();
    } catch {
      // 忽略：某些瀏覽器在非使用者手勢下會 reject
    }
  }
}

export function notify(title: string, body: string): void {
  if (!("Notification" in window)) return;
  if (Notification.permission !== "granted") return;
  try {
    new Notification(title, { body });
  } catch {
    // 忽略通知建構失敗
  }
}
