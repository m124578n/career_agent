import { AppShell, Avatar, Burger, Group, NavLink, Stack, Text, UnstyledButton } from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import { useQuery } from "@tanstack/react-query";
import { Link, Outlet, NavLink as RouterNavLink } from "react-router-dom";
import { api } from "./api/client";
import { useAuth } from "./state/auth";
import { Footer } from "./components/Footer";

const NAV = [
  { to: "/home", label: "總覽", tag: "00" },
  { to: "/resume", label: "履歷與目標", tag: "01" },
  { to: "/jobs", label: "職缺契合度", tag: "02" },
  { to: "/applications", label: "追蹤清單", tag: "03" },
  { to: "/about", label: "關於我", tag: "04" },
  { to: "/self-host", label: "本機自架", tag: "05" },
];

export function GatedLayout() {
  // 行動版：navbar 預設收起，靠 header 的 Burger 開關
  const [opened, { toggle, close }] = useDisclosure(false);
  const { data: quota } = useQuery({ queryKey: ["quota"], queryFn: api.quota });
  const nav = quota?.is_admin
    ? [...NAV, { to: "/admin", label: "營運數據", tag: "06" }]
    : NAV;

  return (
    <AppShell
      header={{ height: { base: 52, sm: 0 } }}
      navbar={{ width: 232, breakpoint: "sm", collapsed: { mobile: !opened } }}
      padding={0}
    >
      <AppShell.Header
        hiddenFrom="sm"
        px="md"
        style={{ background: "var(--jt-panel)", borderColor: "var(--jt-border)" }}
      >
        <Group h="100%" justify="space-between">
          <Link to="/home" className="jt-brand" style={{ textDecoration: "none" }}>
            JobTracker<span className="dot">.</span>
          </Link>
          <Burger
            opened={opened}
            onClick={toggle}
            size="sm"
            aria-label={opened ? "關閉導覽選單" : "開啟導覽選單"}
          />
        </Group>
      </AppShell.Header>

      <AppShell.Navbar
        p="md"
        style={{
          background: "var(--jt-panel)",
          borderColor: "var(--jt-border)",
          display: "flex",
          flexDirection: "column",
        }}
      >
        <Stack gap={2} mb="xl" px={6} pt={4} visibleFrom="sm">
          <Link to="/home" className="jt-brand" style={{ textDecoration: "none" }}>
            JobTracker<span className="dot">.</span>
          </Link>
          <span className="jt-brandtag">AI 求職指揮艙</span>
        </Stack>

        <Stack gap={4}>
          {nav.map((item) => (
            <NavLink
              key={item.to}
              component={RouterNavLink}
              to={item.to}
              label={item.label}
              onClick={close}
              leftSection={
                <span
                  style={{
                    fontFamily: "var(--mantine-font-family-monospace)",
                    fontSize: 11,
                    color: "var(--jt-dim)",
                  }}
                >
                  {item.tag}
                </span>
              }
              styles={{
                root: { borderRadius: 8 },
                label: { fontSize: 14, fontWeight: 500 },
              }}
            />
          ))}
        </Stack>

        <div style={{ marginTop: "auto" }}>
          <AccountFooter />
          <Footer />
        </div>
      </AppShell.Navbar>

      <AppShell.Main style={{ minHeight: "100dvh" }}>
        <Outlet />
      </AppShell.Main>
    </AppShell>
  );
}

function AccountFooter() {
  const { enabled, user, logout } = useAuth();
  // 用量改事件驅動刷新（耗額度的操作完成時 invalidate），輪詢僅作兜底拉長到 60s
  const { data: quota } = useQuery({
    queryKey: ["quota"],
    queryFn: api.quota,
    refetchInterval: 60000,
  });
  const { data: usage } = useQuery({
    queryKey: ["usage"],
    queryFn: api.usage,
    refetchInterval: 60000,
  });
  const { data: globalUsage } = useQuery({
    queryKey: ["usage-global"],
    queryFn: api.globalUsage,
    refetchInterval: 60000,
    enabled: !!quota?.is_admin, // 僅 admin 撈全站
  });

  return (
    <Stack
      gap={12}
      style={{ borderTop: "1px solid var(--jt-border)", paddingTop: 12 }}
      px={6}
    >
      {/* 今日額度 */}
      <div>
        <div className="jt-eyebrow">今日額度</div>
        <div
          style={{
            fontFamily: "var(--mantine-font-family-monospace)",
            fontSize: 17,
            fontWeight: 600,
            color: "var(--jt-text)",
            marginTop: 4,
          }}
        >
          {quota ? `${quota.used} / ${quota.limit}` : "—"}
        </div>
        <div style={{ fontSize: 11, color: "var(--jt-dim)" }}>
          還可用 {quota?.remaining ?? "—"} 次 · 每日重置
        </div>
      </div>

      {/* 個人 token；admin 另看全站 */}
      <div>
        <Text fz={11} c="dimmed" ff="monospace">
          我的 {(usage?.total_tokens ?? 0).toLocaleString()} tokens
        </Text>
        {quota?.is_admin && (
          <Text fz={11} c="tangerine.5" ff="monospace">
            全站 {(globalUsage?.total_tokens ?? 0).toLocaleString()} tokens
          </Text>
        )}
      </div>

      {/* 使用者 + 登出 */}
      {enabled && user && (
        <Group gap={8} wrap="nowrap">
          <Avatar src={user.picture} size={26} radius="xl">
            {user.email[0]?.toUpperCase()}
          </Avatar>
          <div style={{ minWidth: 0, flex: 1 }}>
            <Text fz={12} truncate c="var(--jt-text)">
              {user.name ?? user.email}
            </Text>
            <UnstyledButton onClick={logout} aria-label="登出">
              <Text fz={11} c="tangerine.5">登出</Text>
            </UnstyledButton>
          </div>
        </Group>
      )}
    </Stack>
  );
}
