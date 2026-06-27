// 輕量內聯 SVG icon（零依賴）。line 風格、24x24、用 currentColor 跟著文字色走。
type IconProps = { size?: number; "aria-label"?: string };

function svgProps(size: number, label?: string) {
  return {
    width: size,
    height: size,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 2,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    role: label ? "img" : undefined,
    "aria-label": label,
    "aria-hidden": label ? undefined : true,
  };
}

export function IconX({ size = 16, ...rest }: IconProps) {
  return (
    <svg {...svgProps(size, rest["aria-label"])}>
      <path d="M18 6 6 18M6 6l12 12" />
    </svg>
  );
}

export function IconCoffee({ size = 16, ...rest }: IconProps) {
  return (
    <svg {...svgProps(size, rest["aria-label"])}>
      <path d="M17 8h1a4 4 0 0 1 0 8h-1" />
      <path d="M3 8h14v9a4 4 0 0 1-4 4H7a4 4 0 0 1-4-4V8Z" />
      <path d="M6 2v2M10 2v2M14 2v2" />
    </svg>
  );
}

export function IconMessage({ size = 14, ...rest }: IconProps) {
  return (
    <svg {...svgProps(size, rest["aria-label"])}>
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2Z" />
    </svg>
  );
}

export function IconCoin({ size = 14, ...rest }: IconProps) {
  return (
    <svg {...svgProps(size, rest["aria-label"])}>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v10M9.5 9.5h3.5a1.5 1.5 0 0 1 0 3h-2a1.5 1.5 0 0 0 0 3H14" />
    </svg>
  );
}

export function IconFileText({ size = 24, ...rest }: IconProps) {
  return (
    <svg {...svgProps(size, rest["aria-label"])}>
      <path d="M14 3v4a1 1 0 0 0 1 1h4" />
      <path d="M17 21H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h7l5 5v11a2 2 0 0 1-2 2Z" />
      <path d="M9 13h6M9 17h6" />
    </svg>
  );
}

export function IconTarget({ size = 24, ...rest }: IconProps) {
  return (
    <svg {...svgProps(size, rest["aria-label"])}>
      <circle cx="12" cy="12" r="9" />
      <circle cx="12" cy="12" r="5" />
      <circle cx="12" cy="12" r="1" />
    </svg>
  );
}

export function IconPenLine({ size = 24, ...rest }: IconProps) {
  return (
    <svg {...svgProps(size, rest["aria-label"])}>
      <path d="M12 20h9" />
      <path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z" />
    </svg>
  );
}

export function IconClipboardCheck({ size = 24, ...rest }: IconProps) {
  return (
    <svg {...svgProps(size, rest["aria-label"])}>
      <rect x="8" y="3" width="8" height="4" rx="1" />
      <path d="M16 5h2a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h2" />
      <path d="m9 14 2 2 4-4" />
    </svg>
  );
}
