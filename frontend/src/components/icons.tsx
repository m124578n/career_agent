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
