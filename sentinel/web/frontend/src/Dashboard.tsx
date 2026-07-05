import { ActionIcon, Anchor, Badge, Button, Grid, Group, Paper, Text, Title } from "@mantine/core";
import { IconAlertTriangle, IconArrowBackUp, IconCalendarPlus, IconCheck, IconMessageCircle, IconStarFilled, IconX } from "@tabler/icons-react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { type PipelineJob, dismissInterview, getSnapshot, getStatus, restoreInterview, untrackJob } from "./api";
import JobCardDrawer, { type CardJob } from "./JobCardDrawer";
import ResearchButton from "./ResearchButton";
import { Kpi, PageContainer } from "./ui";

const SHOW_LIMIT = 8; // 清單預設顯示筆數，超過收合

function SectionTitle({ children, id }: { children: React.ReactNode; id?: string }) {
  return (
    <Title id={id} order={5} mb="sm" style={{ letterSpacing: "-0.3px", scrollMarginTop: 24 }}>
      {children}
    </Title>
  );
}

function Row({ children }: { children: React.ReactNode }) {
  return (
    <Group justify="space-between" wrap="nowrap" px="md" py={10} mb={6}
      bg="dark.6" className="flat-row" style={{ borderRadius: 8, transition: "background-color 200ms" }}>
      {children}
    </Group>
  );
}

function ShowAll({ total, showAll, onToggle }: { total: number; showAll: boolean; onToggle: () => void }) {
  if (total <= SHOW_LIMIT) return null;
  return (
    <Button variant="subtle" color="gray" size="compact-xs" onClick={onToggle}>
      {showAll ? "收合" : `顯示全部 ${total} 筆`}
    </Button>
  );
}

const Star = () => (
  <IconStarFilled size={12} style={{ color: "var(--mantine-color-tangerine-5)", flexShrink: 0 }} />
);

/** 公司名連結：優先用該筆資料的職缺頁，否則連 104 公司搜尋 */
function CompanyLink({ name, href }: { name: string; href?: string }) {
  const url = href || `https://www.104.com.tw/company/search/?keyword=${encodeURIComponent(name)}`;
  return (
    <Anchor href={url} target="_blank" size="sm" fw={600} c="dark.0" underline="hover">
      {name}
    </Anchor>
  );
}

export default function Dashboard() {
  const snap = useQuery({ queryKey: ["snapshot"], queryFn: getSnapshot });
  const status = useQuery({ queryKey: ["status"], queryFn: getStatus });
  const s = snap.data;
  const invites = s?.messages.filter((m) => m.has_interview_invite).length ?? 0;
  const newViewers = status.data?.last_change_counts?.new_viewers ?? 0;

  const qc = useQueryClient();
  const [allViewers, setAllViewers] = useState(false);
  const [allMsgs, setAllMsgs] = useState(false);
  const [showDone, setShowDone] = useState(false);
  const [cardJob, setCardJob] = useState<CardJob | null>(null);
  const openCard = (j: PipelineJob) => () =>
    setCardJob({ code: j.code, company: j.company, title: j.title, url: j.job_url || j.url, salary: j.salary });

  const pipe = s?.pipeline ?? [];
  const interviewing = pipe.filter((j) => j.state === "interviewing");
  const upcomingJobs = interviewing.filter((j) => !j.dismissed);
  const doneJobs = interviewing.filter((j) => j.dismissed);
  const appliedJobs = pipe.filter((j) => j.state === "applied");
  const interestedJobs = pipe.filter((j) => j.state === "interested");
  const matchedJobs = pipe.filter((j) => j.state === "matched");
  const tailoredJobs = pipe.filter((j) => j.state === "tailored");

  // 排序：面試中依 when、已投遞依 applied_at 升冪；三手動群組依 match_score 降冪（無分數殿後）
  const byWhen = (a: PipelineJob, b: PipelineJob) => (a.when || "").localeCompare(b.when || "");
  const byApplied = (a: PipelineJob, b: PipelineJob) => (a.applied_at || "").localeCompare(b.applied_at || "");
  const byScore = (a: PipelineJob, b: PipelineJob) => (b.match_score ?? -1) - (a.match_score ?? -1);
  const upcomingSorted = [...upcomingJobs].sort(byWhen);
  const appliedSorted = [...appliedJobs].sort(byApplied);
  const matchedSorted = [...matchedJobs].sort(byScore);
  const tailoredSorted = [...tailoredJobs].sort(byScore);

  const untrack = (code: string) => async () => {
    try {
      await untrackJob(code);
      qc.invalidateQueries({ queryKey: ["snapshot"] });
    } catch { window.alert("網路錯誤，請重試"); }
  };

  const ackInterview = (key: string) => async () => {
    try {
      await dismissInterview(key);
      qc.invalidateQueries({ queryKey: ["snapshot"] });
    } catch { window.alert("網路錯誤，請重試"); }
  };
  const unackInterview = (key: string) => async () => {
    try {
      await restoreInterview(key);
      qc.invalidateQueries({ queryKey: ["snapshot"] });
    } catch { window.alert("網路錯誤，請重試"); }
  };

  const viewers = s ? (allViewers ? s.viewers : s.viewers.slice(0, SHOW_LIMIT)) : [];
  const msgs = s ? (allMsgs ? s.messages : s.messages.slice(0, SHOW_LIMIT)) : [];

  const jump = (id: string) => () =>
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });

  return (
    <PageContainer size="lg">
      <Group gap={52} align="flex-start">
        <div onClick={jump("sec-viewers")} style={{ cursor: "pointer" }}>
          <Kpi
            value={s?.viewers.length ?? "—"}
            label="誰看過我"
            suffix={newViewers > 0 ? <Text span c="teal.5" ff="monospace" size="md">+{newViewers}</Text> : undefined}
          />
        </div>
        <div onClick={jump("sec-pipeline")} style={{ cursor: "pointer" }}>
          <Kpi value={s ? upcomingJobs.length : "—"} label="即將面試" />
        </div>
        <div onClick={jump("sec-messages")} style={{ cursor: "pointer" }}>
          <Kpi
            value={s?.messages.length ?? "—"}
            label="新訊息"
            suffix={invites > 0 ? <Text span c="amber.5" ff="monospace" size="md">{invites} 邀約</Text> : undefined}
          />
        </div>
        <div onClick={jump("sec-pipeline")} style={{ cursor: "pointer" }}>
          <Kpi value={s?.applications.length ?? "—"} label="投遞中" />
        </div>
      </Group>

      {status.data?.last_error && (
        <Group gap={6} mt="lg">
          <IconAlertTriangle size={15} style={{ color: "var(--mantine-color-danger-6)" }} />
          <Text c="danger.6" size="sm">{status.data.last_error}</Text>
        </Group>
      )}
      {s && s.failed_readers.length > 0 && (
        <Group gap={6} mt="sm">
          <IconAlertTriangle size={15} style={{ color: "var(--mantine-color-amber-5)" }} />
          <Text c="amber.5" size="sm">本次未讀到：{s.failed_readers.join("、")}（沿用上次）</Text>
        </Group>
      )}

      <Paper bg="dark.6" radius="md" p="lg" mt={28}>
        <Text size="xs" c="dimmed" mb={6} style={{ letterSpacing: 2 }}>今日彙整</Text>
        <Text size="sm" c="dark.1" style={{ whiteSpace: "pre-wrap", lineHeight: 1.7 }}>
          {s?.digest ?? "載入中…"}
        </Text>
      </Paper>

      {s && (upcomingJobs.length > 0 || appliedJobs.length > 0 || doneJobs.length > 0 || tailoredSorted.length > 0 || matchedSorted.length > 0 || interestedJobs.length > 0) && (
        <div style={{ marginTop: 32 }}>
          <SectionTitle id="sec-pipeline">職缺管道</SectionTitle>

          {upcomingJobs.length > 0 && (
            <>
              <Text size="xs" c="teal.5" mb={6} mt="xs" fw={600} style={{ letterSpacing: 1 }}>面試中</Text>
              {upcomingSorted.map((j: PipelineJob) => (
                <Row key={j.key}>
                  <div onClick={openCard(j)} style={{ cursor: "pointer", minWidth: 0, flex: 1 }}>
                    <Text size="sm" truncate>
                      <CompanyLink name={j.company} href={j.job_url || j.company_url || undefined} />
                      <Text span c="dimmed"> · {j.title}{j.location ? ` · ${j.location}` : ""}</Text>
                    </Text>
                  </div>
                  <span onClick={(e) => e.stopPropagation()}>
                    <ResearchButton company={j.company} />
                  </span>
                  <Group gap="md" wrap="nowrap" style={{ flexShrink: 0 }}>
                    <Text c="teal.5" ff="monospace" size="xs">{j.when || "日期未擷取"}</Text>
                    {j.job_url && (
                      <Anchor href={j.job_url} target="_blank" size="xs" c="dimmed"
                        onClick={(e) => e.stopPropagation()}>看職缺</Anchor>
                    )}
                    {j.thread_url && (
                      <ActionIcon component="a" href={j.thread_url} target="_blank"
                        variant="default" size="md" title="開啟 104 對話"
                        onClick={(e) => e.stopPropagation()}>
                        <IconMessageCircle size={15} />
                      </ActionIcon>
                    )}
                    <ActionIcon component="a" href={j.gcal_link} target="_blank"
                      variant="default" size="md" title="加入 Google 日曆"
                      onClick={(e) => e.stopPropagation()}>
                      <IconCalendarPlus size={15} />
                    </ActionIcon>
                    <ActionIcon variant="default" size="md" title="知道了（隱藏，可還原）"
                      onClick={(e) => { e.stopPropagation(); ackInterview(j.interview_key)(); }}>
                      <IconCheck size={15} />
                    </ActionIcon>
                  </Group>
                </Row>
              ))}
            </>
          )}

          {doneJobs.length > 0 && (
            <>
              <Button variant="subtle" color="gray" size="compact-xs" onClick={() => setShowDone((v) => !v)}>
                {showDone ? "收合已處理" : `已處理 ${doneJobs.length} 場`}
              </Button>
              {showDone && doneJobs.map((j: PipelineJob) => (
                <Row key={j.key}>
                  <Text size="sm" truncate style={{ opacity: 0.55, minWidth: 0, flex: 1 }}>
                    <Text span fw={600}>{j.company}</Text>
                    <Text span c="dimmed"> · {j.title} · {j.when || "日期未擷取"}</Text>
                  </Text>
                  <ActionIcon variant="subtle" color="gray" size="md" title="還原到清單" style={{ flexShrink: 0 }}
                    onClick={unackInterview(j.interview_key)}>
                    <IconArrowBackUp size={15} />
                  </ActionIcon>
                </Row>
              ))}
            </>
          )}

          {appliedJobs.length > 0 && (
            <>
              <Text size="xs" c="dimmed" mb={6} mt="md" fw={600} style={{ letterSpacing: 1 }}>已投遞</Text>
              {appliedSorted.map((j: PipelineJob) => (
                <Row key={j.key}>
                  <Group gap={8} wrap="nowrap" style={{ minWidth: 0, flex: 1, cursor: "pointer" }} onClick={openCard(j)}>
                    {j.watched && <Star />}
                    <Text size="sm" truncate>
                      <CompanyLink name={j.company} href={j.company_url || undefined} />
                      <Text span c="dimmed"> · </Text>
                      {j.job_url ? (
                        <Anchor href={j.job_url} target="_blank" size="sm" c="dimmed" underline="hover"
                          onClick={(e) => e.stopPropagation()}>{j.title}</Anchor>
                      ) : (
                        <Text span c="dimmed">{j.title}</Text>
                      )}
                    </Text>
                    <span onClick={(e) => e.stopPropagation()}>
                      <ResearchButton company={j.company} />
                    </span>
                  </Group>
                  {j.status && <Badge size="sm" variant="light" color="teal">{j.status}</Badge>}
                </Row>
              ))}
            </>
          )}

          {tailoredSorted.length > 0 && (
            <>
              <Text size="xs" c="dimmed" mb={6} mt="md" fw={600} style={{ letterSpacing: 1 }}>已客製化</Text>
              {tailoredSorted.map((j: PipelineJob) => (
                <Row key={j.key}>
                  <Group gap={8} wrap="nowrap" style={{ minWidth: 0, flex: 1, cursor: "pointer" }} onClick={openCard(j)}>
                    {j.watched && <Star />}
                    <Text size="sm" truncate>
                      <CompanyLink name={j.company} href={j.job_url || j.company_url || undefined} />
                      <Text span c="dimmed"> · {j.title}</Text>
                    </Text>
                    <span onClick={(e) => e.stopPropagation()}>
                      <ResearchButton company={j.company} />
                    </span>
                  </Group>
                  <ActionIcon variant="subtle" color="gray" size="sm" title="取消追蹤" style={{ flexShrink: 0 }}
                    onClick={(e) => { e.stopPropagation(); untrack(j.code)(); }}>
                    <IconX size={14} />
                  </ActionIcon>
                </Row>
              ))}
            </>
          )}

          {matchedSorted.length > 0 && (
            <>
              <Text size="xs" c="dimmed" mb={6} mt="md" fw={600} style={{ letterSpacing: 1 }}>已比對</Text>
              {matchedSorted.map((j: PipelineJob) => (
                <Row key={j.key}>
                  <Group gap={8} wrap="nowrap" style={{ minWidth: 0, flex: 1, cursor: "pointer" }} onClick={openCard(j)}>
                    {j.watched && <Star />}
                    <Text size="sm" truncate>
                      <CompanyLink name={j.company} href={j.job_url || j.company_url || undefined} />
                      <Text span c="dimmed"> · {j.title}</Text>
                    </Text>
                    {j.match_score != null && <Badge size="sm" variant="light" color="teal">{j.match_score}</Badge>}
                    <span onClick={(e) => e.stopPropagation()}>
                      <ResearchButton company={j.company} />
                    </span>
                  </Group>
                  <ActionIcon variant="subtle" color="gray" size="sm" title="取消追蹤" style={{ flexShrink: 0 }}
                    onClick={(e) => { e.stopPropagation(); untrack(j.code)(); }}>
                    <IconX size={14} />
                  </ActionIcon>
                </Row>
              ))}
            </>
          )}

          {interestedJobs.length > 0 && (
            <>
              <Text size="xs" c="dimmed" mb={6} mt="md" fw={600} style={{ letterSpacing: 1 }}>有興趣</Text>
              {interestedJobs.map((j: PipelineJob) => (
                <Row key={j.key}>
                  <Group gap={8} wrap="nowrap" style={{ minWidth: 0, flex: 1, cursor: "pointer" }} onClick={openCard(j)}>
                    {j.watched && <Star />}
                    <Text size="sm" truncate>
                      <CompanyLink name={j.company} href={j.job_url || j.company_url || undefined} />
                      <Text span c="dimmed"> · {j.title}</Text>
                    </Text>
                    <span onClick={(e) => e.stopPropagation()}>
                      <ResearchButton company={j.company} />
                    </span>
                  </Group>
                  <ActionIcon variant="subtle" color="gray" size="sm" title="取消追蹤" style={{ flexShrink: 0 }}
                    onClick={(e) => { e.stopPropagation(); untrack(j.code)(); }}>
                    <IconX size={14} />
                  </ActionIcon>
                </Row>
              ))}
            </>
          )}
        </div>
      )}

      <Grid mt={32} gutter={36}>
        <Grid.Col span={6}>
          <SectionTitle id="sec-viewers">誰看過我</SectionTitle>
          {viewers.map((v, i) => (
            <Row key={i}>
              <Group gap={8} wrap="nowrap" style={{ minWidth: 0 }}>
                {v.watched && <Star />}
                <Text size="sm" truncate>
                  <CompanyLink name={v.company} href={v.company_url || undefined} />
                  <Text span c="dimmed"> · {v.job_title}</Text>
                </Text>
                <ResearchButton company={v.company} />
              </Group>
              <Text c="dimmed" ff="monospace" size="xs">{v.viewed_at}</Text>
            </Row>
          ))}
          <ShowAll total={s?.viewers.length ?? 0} showAll={allViewers} onToggle={() => setAllViewers((v) => !v)} />
        </Grid.Col>

        <Grid.Col span={6}>
          <SectionTitle id="sec-messages">訊息 · 面試</SectionTitle>
          {msgs.map((m) => (
            <Row key={m.thread_id}>
              <Group gap={8} wrap="nowrap" style={{ minWidth: 0, flex: 1 }}>
                {m.has_interview_invite && <Badge size="xs" variant="light" color="amber">面試</Badge>}
                {m.watched && <Star />}
                <Text size="sm" truncate>
                  <CompanyLink name={m.company} href={m.company_url || undefined} />
                  <Text span c="dimmed">：{m.last_message}</Text>
                </Text>
                <ResearchButton company={m.company} />
              </Group>
              {m.thread_url && (
                <ActionIcon component="a" href={m.thread_url} target="_blank"
                  variant="subtle" color="gray" size="sm" title="開啟 104 對話" style={{ flexShrink: 0 }}>
                  <IconMessageCircle size={14} />
                </ActionIcon>
              )}
            </Row>
          ))}
          <ShowAll total={s?.messages.length ?? 0} showAll={allMsgs} onToggle={() => setAllMsgs((v) => !v)} />
        </Grid.Col>
      </Grid>

      <JobCardDrawer job={cardJob} opened={cardJob !== null} onClose={() => setCardJob(null)} />
    </PageContainer>
  );
}
