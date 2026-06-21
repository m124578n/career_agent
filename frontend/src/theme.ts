import { createTheme, type MantineColorsTuple } from "@mantine/core";

// Cockpit 指揮艙：偏冷的 ink 底 + 雙訊號色（tangerine 行動 / teal 契合）

const tangerine: MantineColorsTuple = [
  "#fff0eb", "#ffd9cc", "#ffb59e", "#ff8f6f", "#ff7048",
  "#ff6a3d", "#f15a2c", "#cf4a22", "#a83b1a", "#7d2b12",
];

const teal: MantineColorsTuple = [
  "#e1fbf6", "#bff3ea", "#92ebdd", "#5fe2cf", "#3fd9c5",
  "#34d6c8", "#22b3a6", "#198f86", "#136d66", "#0c4a45",
];

// 覆寫 Mantine 的 dark 色階 → 整個深色介面用我們的 ink 調
const ink: MantineColorsTuple = [
  "#E6E8EB", // 0 主要文字
  "#C2C7CE", // 1
  "#9AA1AB", // 2 muted
  "#6B727C", // 3 dim
  "#2A2E36", // 4 邊框
  "#23272F", // 5
  "#1E2127", // 6 面板
  "#14161A", // 7 body 背景
  "#0F1115", // 8
  "#0A0B0E", // 9
];

export const theme = createTheme({
  fontFamily: "'IBM Plex Sans', system-ui, sans-serif",
  fontFamilyMonospace: "'IBM Plex Mono', ui-monospace, monospace",
  headings: { fontFamily: "'Space Grotesk', system-ui, sans-serif" },
  primaryColor: "tangerine",
  primaryShade: 5,
  defaultRadius: "sm",
  colors: { tangerine, teal, dark: ink },
});
