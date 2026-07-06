import { Alert, AppShell, Button, Group } from "@mantine/core";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { ackSchedule, getSchedule, getStatus, startScrape } from "./api";
import ChatPage from "./ChatPage";
import Dashboard from "./Dashboard";
import FindJobsPage from "./FindJobsPage";
import { ensurePermission, notify } from "./notify";
import ProfilePage from "./ProfilePage";
import ScrapeStepper from "./ScrapeStepper";
import SettingsModal from "./SettingsModal";
import Sidebar, { type PageKey } from "./Sidebar";

export default function App() {
  const qc = useQueryClient();
  const [page, setPage] = useState<PageKey>("dashboard");
  const [polling, setPolling] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const prevDue = useRef(false);
  const notifyOnDone = useRef(false);
  const sawRunning = useRef(false);
  const baseline = useRef<{ run: string | null; err: string | null }>({ run: null, err: null });

  const status = useQuery({
    queryKey: ["status"], queryFn: getStatus,
    refetchInterval: polling ? 2000 : false,
  });
  const schedule = useQuery({ queryKey: ["schedule"], queryFn: getSchedule, refetchInterval: 30000 });

  useEffect(() => { ensurePermission(); }, []);

  // 到點：due false→true 邊緣 → 桌面通知（橫幅由 schedule.data.due 直接驅動）
  useEffect(() => {
    const due = schedule.data?.due ?? false;
    if (due && !prevDue.current) {
      notify("⏰ career-sentinel", "該檢視求職動態了，點「立即拉取」更新。");
    }
    prevDue.current = due;
  }, [schedule.data?.due]);

  // scrape 完成偵測：只有「觀察到 running=true 過」或「last_run/last_error 真的相對抓取前變了」才算完成，
  // 避免用抓取前的 stale idle 狀態（running=false）在剛 setPolling(true) 時就誤判完成、提早停輪詢。
  useEffect(() => {
    if (!polling || !status.data) return;
    const s = status.data;
    if (s.running) { sawRunning.current = true; return; }
    const changed = s.last_run !== baseline.current.run || s.last_error !== baseline.current.err;
    if (!sawRunning.current && !changed) return;  // 仍是抓取前的 stale idle，別誤判完成
    setPolling(false);
    qc.invalidateQueries({ queryKey: ["snapshot"] });
    const c = s.last_change_counts;
    const total = c ? c.new_viewers + c.status_changes + c.new_messages + c.new_invites : 0;
    if (notifyOnDone.current && !s.last_error && total > 0) {
      notify("🔔 career-sentinel", `發現 ${total} 筆新動態（看過我／訊息／狀態變化）。`);
    }
    notifyOnDone.current = false;
    sawRunning.current = false;
  }, [polling, status.data, qc]);

  async function refresh() {
    const r = await startScrape();
    notifyOnDone.current = r.status !== "already_running";
    sawRunning.current = false;
    baseline.current = { run: status.data?.last_run ?? null, err: status.data?.last_error ?? null };
    setPolling(true);
    qc.invalidateQueries({ queryKey: ["status"] });  // 強刷 status，盡快觀察到 running=true
  }

  async function onBannerPull() {
    await ackSchedule();
    qc.invalidateQueries({ queryKey: ["schedule"] });
    prevDue.current = false;
    await refresh();
  }

  async function onBannerDismiss() {
    await ackSchedule();
    qc.invalidateQueries({ queryKey: ["schedule"] });
    prevDue.current = false;
  }

  const running = polling || !!status.data?.running;
  const due = schedule.data?.due ?? false;

  return (
    <AppShell navbar={{ width: 200, breakpoint: 0 }} padding={0}>
      <AppShell.Navbar>
        <Sidebar
          page={page}
          onNavigate={setPage}
          onRefresh={refresh}
          running={running}
          lastRun={status.data?.last_run ?? null}
          onOpenSettings={() => setSettingsOpen(true)}
        />
      </AppShell.Navbar>
      <AppShell.Main>
        <ScrapeStepper phase={status.data?.phase ?? ""} />
        {due && (
          <Alert color="amber" m="md" mb={0} withCloseButton onClose={onBannerDismiss} title="該檢視求職動態了">
            <Group>
              <Button size="xs" onClick={onBannerPull} loading={running} disabled={running}>立即拉取</Button>
              <Button size="xs" variant="light" onClick={() => setPage("jobs")}>也拉推薦</Button>
            </Group>
          </Alert>
        )}
        {/* 所有分頁保持掛載、以 display:none 切換——切分頁不卸載，保住各頁結果與
            進行中的操作狀態（原本只有聊天頁這樣做，其餘條件掛載會在切走時清空 local state）。
            各頁 mount 時只 seed 表單、不自動觸發爬蟲/LLM，故全掛載安全。 */}
        <div style={{ display: page === "dashboard" ? undefined : "none" }}><Dashboard /></div>
        <div style={{ display: page === "resume" ? undefined : "none" }}><ProfilePage /></div>
        <div style={{ display: page === "jobs" ? undefined : "none" }}><FindJobsPage /></div>
        <div style={{ display: page === "chat" ? undefined : "none" }}><ChatPage /></div>
      </AppShell.Main>
      <SettingsModal opened={settingsOpen} onClose={() => setSettingsOpen(false)} />
    </AppShell>
  );
}
