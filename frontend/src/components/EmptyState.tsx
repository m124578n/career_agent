import type { ReactNode } from "react";

/** 友善空狀態：標題 + 說明 +（可選）下一步動作 */
export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="jt-empty">
      <div className="jt-empty-title">{title}</div>
      <div className="jt-empty-desc">{description}</div>
      {action && <div style={{ marginTop: 16 }}>{action}</div>}
    </div>
  );
}
