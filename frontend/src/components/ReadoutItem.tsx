import type { ReactNode } from "react";

/** 診斷項目列：圓點標記 + 淡色襯底。kind=pos 亮點（teal）/ warn 可加強（amber） */
export function ReadoutItem({
  kind,
  children,
}: {
  kind: "pos" | "warn";
  children: ReactNode;
}) {
  return (
    <div className="jt-item" data-kind={kind}>
      <span className="jt-dot" data-kind={kind} aria-hidden />
      <span>{children}</span>
    </div>
  );
}
