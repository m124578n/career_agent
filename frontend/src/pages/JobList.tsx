import {
  ActionIcon,
  Box,
  Button,
  Checkbox,
  CopyButton,
  Group,
  Loader,
  Modal,
  MultiSelect,
  Stack,
  Text,
  Textarea,
  TextInput,
  Title,
  UnstyledButton,
} from "@mantine/core";
import { IconX } from "../components/icons";
import { useDisclosure } from "@mantine/hooks";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import { useResume } from "../state/resume";
import { REGIONS } from "../constants/regions";
import { AnalyzingSteps } from "../components/AnalyzingSteps";
import type { JobMatch } from "../types";

// 持久化搜尋狀態，切到別頁再切回來不會被清空
const KW_KEY = "jobtracker.job-keyword";
const AREA_KEY = "jobtracker.job-area";
const SEL_KEY = "jobtracker.selected-search";

export function JobList() {
  const { target } = useResume();
  const [keyword, setKeyword] = useState(() => localStorage.getItem(KW_KEY) ?? "");
  const [area, setArea] = useState<string[]>(() => {
    try {
      return JSON.parse(localStorage.getItem(AREA_KEY) ?? "[]");
    } catch {
      return [];
    }
  });
  const [selectedId, setSelectedId] = useState<string | null>(() =>
    localStorage.getItem(SEL_KEY)
  );
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [resultLimit, setResultLimit] = useState(12); // 排序結果漸進顯示
  const [candOpen, setCandOpen] = useState(true);
  const qc = useQueryClient();

  // 耗額度的操作完成時主動刷新用量（取代高頻輪詢）
  const refreshUsage = () => {
    qc.invalidateQueries({ queryKey: ["quota"] });
    qc.invalidateQueries({ queryKey: ["usage"] });
    qc.invalidateQueries({ queryKey: ["usage-global"] });
  };

  const searchesQ = useQuery({ queryKey: ["searches"], queryFn: api.listSearches });

  const agentQ = useQuery({
    queryKey: ["agent-status"],
    queryFn: api.agentStatus,
    refetchInterval: 15000,
  });

  const searchQ = useQuery({
    queryKey: ["search", selectedId],
    queryFn: () => api.getSearch(selectedId!),
    enabled: !!selectedId,
    refetchInterval: (q) =>
      ["queued", "crawling"].includes(q.state.data?.crawl_status ?? "") ? 2500 : false,
  });
  const crawlStatus = searchQ.data?.crawl_status;

  const matchesQ = useQuery({
    queryKey: ["search-matches", selectedId],
    queryFn: () => api.searchMatches(selectedId!),
    enabled: !!selectedId,
    refetchInterval: (q) => {
      const hasPending = (q.state.data ?? []).some((m) => m.status === "pending");
      const crawling = ["queued", "crawling"].includes(crawlStatus ?? "");
      return hasPending || crawling ? 2500 : false;
    },
  });
  const matches = matchesQ.data ?? [];
  const candidates = matches.filter((m) => m.status === "candidate");
  const results = matches.filter((m) => m.status !== "candidate");

  // 持久化搜尋狀態（切頁不清空）
  useEffect(() => {
    localStorage.setItem(KW_KEY, keyword);
  }, [keyword]);
  useEffect(() => {
    localStorage.setItem(AREA_KEY, JSON.stringify(area));
  }, [area]);
  useEffect(() => {
    if (selectedId) localStorage.setItem(SEL_KEY, selectedId);
    else localStorage.removeItem(SEL_KEY);
    setResultLimit(12); // 切換搜尋時重置展開筆數
  }, [selectedId]);
  // 還原的選中搜尋若已被刪除（不在歷史列表），清掉避免空白／404
  useEffect(() => {
    if (
      selectedId &&
      searchesQ.data &&
      !searchesQ.data.some((s) => s.search_id === selectedId)
    ) {
      setSelectedId(null);
    }
  }, [selectedId, searchesQ.data]);
  // 非同步分析從「有 pending」變「全部結束」時，token 才落定 → 刷一次用量
  const hadPending = useRef(false);
  useEffect(() => {
    const has = matches.some((m) => m.status === "pending");
    if (hadPending.current && !has) refreshUsage();
    hadPending.current = has;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [matches]);

  // 自動勾選 relevant 候選：每個搜尋只在候選首次到達時預選 relevant === true 的職缺，
  // 之後即使使用者手動取消全選、candidates 參照因 poll 更新，也不會再覆蓋。
  const autoPickedRef = useRef<string | null>(null);
  useEffect(() => {
    if (!selectedId || candidates.length === 0) return;
    if (autoPickedRef.current === selectedId) return; // 已對此搜尋自動勾選過
    autoPickedRef.current = selectedId;
    if (picked.size > 0) return; // 已有勾選（理論上首次不會，但保險起見）
    const relevant = new Set(
      candidates.filter((c) => c.relevant).map((c) => c.job.job_id)
    );
    if (relevant.size > 0) setPicked(relevant);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [candidates, selectedId]);

  const createMut = useMutation({
    mutationFn: api.createSearch,
    onSuccess: (data) => {
      setSelectedId(data.search_id);
      setPicked(new Set());
      qc.invalidateQueries({ queryKey: ["searches"] });
      qc.invalidateQueries({ queryKey: ["search-matches", data.search_id] });
    },
  });
  const crawlMut = useMutation({
    mutationFn: () => api.crawlNext(selectedId!),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["searches"] });
      qc.invalidateQueries({ queryKey: ["search-matches", selectedId] });
    },
  });
  const analyzeMut = useMutation({
    // 只送「仍是候選」的職缺：picked 可能含已分析過的 id，
    // 若一併送出會被後端 set_pending 打回重跑、重複耗額度。
    mutationFn: () =>
      api.analyzeSelected(
        selectedId!,
        candidates.filter((c) => picked.has(c.job.job_id)).map((c) => c.job.job_id)
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["search-matches", selectedId] });
      refreshUsage(); // 送出即可能扣次數，先刷 quota
    },
  });
  const delMut = useMutation({
    mutationFn: api.deleteSearch,
    onSuccess: (_d, sid) => {
      if (sid === selectedId) setSelectedId(null);
      qc.invalidateQueries({ queryKey: ["searches"] });
    },
  });

  const toggle = (id: string) =>
    setPicked((p) => { const n = new Set(p); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const pickedCandidates = candidates.filter((c) => picked.has(c.job.job_id));
  const allPicked = candidates.length > 0 && pickedCandidates.length === candidates.length;
  const somePicked = pickedCandidates.length > 0 && !allPicked;
  // 全選／取消全選：只動「候選」的 id，不影響其他狀態
  const toggleAll = () =>
    setPicked((p) => {
      const n = new Set(p);
      if (allPicked) candidates.forEach((c) => n.delete(c.job.job_id));
      else candidates.forEach((c) => n.add(c.job.job_id));
      return n;
    });

  const busy = createMut.isPending || crawlMut.isPending;
  const canRun = !!target && keyword.trim().length > 0 && !busy;
  const run = () => {
    if (target) createMut.mutate({ keyword: keyword.trim(), target, area: area.join(",") || null });
  };

  const searches = searchesQ.data ?? [];

  return (
    <Box p={{ base: "lg", md: 40 }} maw={1180} mx="auto">
      <Stack gap={6} mb={28}>
        <span className="jt-eyebrow">
          職缺 <b>&times;</b> 契合度
        </span>
        <Title order={1} fz={{ base: 28, md: 34 }} fw={700} lts="-0.02em">
          職缺契合度
        </Title>
        <Text c="dimmed" fz="sm" maw={580}>
          輸入關鍵字爬取 104 職缺，勾選有興趣的候選後送出分析，逐筆比對你的履歷並排序。
        </Text>
      </Stack>

      {!target ? (
        <div className="jt-panel">
          <div className="jt-panel-body" data-center="true">
            <div className="jt-empty">
              尚未設定履歷 //{" "}
              <Link to="/resume" style={{ color: "var(--jt-teal)" }}>
                先到「履歷與目標」
              </Link>{" "}
              上傳並設定目標
            </div>
          </div>
        </div>
      ) : (
        <>
          {/* 控制列 */}
          <div className="jt-panel" style={{ marginBottom: 20 }}>
            <div className="jt-panel-body">
              <Group align="flex-end" gap={12} wrap="wrap">
                <TextInput
                  label="搜尋關鍵字"
                  placeholder="例：Python 後端 / AI 工程師"
                  value={keyword}
                  onChange={(e) => setKeyword(e.currentTarget.value)}
                  onKeyDown={(e) => e.key === "Enter" && canRun && run()}
                  style={{ flex: 1, minWidth: 180 }}
                />
                <MultiSelect
                  label="地區（縣市）"
                  placeholder="不選=全台"
                  data={REGIONS}
                  value={area}
                  onChange={setArea}
                  clearable
                  searchable
                  style={{ minWidth: 200 }}
                />
                <Button
                  color="tangerine"
                  size="md"
                  disabled={!canRun}
                  loading={busy}
                  onClick={run}
                >
                  爬取候選
                </Button>
              </Group>
              <Text fz="xs" c="dimmed" mt={8}>
                目標：{target.target_title}
                {target.expected_salary
                  ? ` · 期望 ${target.expected_salary.toLocaleString()}`
                  : ""}
              </Text>
              <Text fz="xs" c={agentQ.data?.online ? "teal" : "dimmed"} mt={8}>
                {agentQ.data?.online ? "🟢 爬蟲在線" : "⚪ 爬蟲離線"}
                {agentQ.data && agentQ.data.pending > 0 ? ` · 排隊 ${agentQ.data.pending}` : ""}
              </Text>
              {(createMut.isError || crawlMut.isError) && (
                <Text fz="xs" c="tangerine.5" mt={6}>
                  爬取失敗：請確認後端與關鍵字後再試。
                </Text>
              )}
            </div>
          </div>

          {/* 歷史 chips */}
          {searches.length > 0 && (
            <div className="jt-panel" style={{ marginBottom: 20 }}>
              <div className="jt-panel-body">
                <Group gap={8} wrap="wrap">
                  {searches.map((s) => {
                    const when = new Date(s.created_at).toLocaleString("zh-TW", {
                      month: "numeric",
                      day: "numeric",
                      hour: "2-digit",
                      minute: "2-digit",
                    });
                    return (
                      <Group
                        key={s.search_id}
                        gap={2}
                        wrap="nowrap"
                        style={{
                          borderRadius: 8,
                          border: "1px solid var(--jt-border)",
                          background:
                            s.search_id === selectedId
                              ? "rgba(52,214,200,0.12)"
                              : "transparent",
                        }}
                      >
                        <UnstyledButton
                          px={10}
                          py={6}
                          aria-label={`查看搜尋 ${s.keyword}`}
                          onClick={() => {
                            setSelectedId(s.search_id);
                            setPicked(new Set());
                          }}
                        >
                          <Text fz="xs">
                            {s.keyword} · {when} · {s.count} 筆
                          </Text>
                        </UnstyledButton>
                        <ActionIcon
                          variant="subtle"
                          color="gray"
                          size="lg"
                          mr={2}
                          aria-label={`刪除搜尋 ${s.keyword}`}
                          onClick={() => delMut.mutate(s.search_id)}
                        >
                          <IconX size={14} />
                        </ActionIcon>
                      </Group>
                    );
                  })}
                </Group>
              </div>
            </div>
          )}

          {/* 爬取中的進度顯示 */}
          {createMut.isPending && (
            <div className="jt-panel" style={{ marginBottom: 20 }}>
              <div className="jt-panel-body">
                <AnalyzingSteps
                  steps={[
                    "連線 104…",
                    "爬取職缺清單…",
                    "標記關鍵字命中…",
                    "整理候選清單…",
                  ]}
                  intervalSec={2}
                />
              </div>
            </div>
          )}

          {/* 候選清單 */}
          {candidates.length > 0 && (
            <div className="jt-panel" style={{ marginBottom: 20 }}>
              <div className="jt-panel-head">
                <span className="jt-eyebrow">候選 // CANDIDATES · {candidates.length}</span>
                <Group gap={8}>
                  <Button size="xs" variant="subtle" color="gray"
                          onClick={() => setCandOpen((o) => !o)}>
                    {candOpen ? "▾ 收合" : "▸ 展開"}
                  </Button>
                  <Button size="xs" variant="default" onClick={() => crawlMut.mutate()}
                          disabled={busy} loading={crawlMut.isPending}>爬下一頁</Button>
                  <Button size="xs" color="tangerine"
                          disabled={pickedCandidates.length === 0 || analyzeMut.isPending}
                          loading={analyzeMut.isPending}
                          onClick={() => analyzeMut.mutate()}>
                    分析選中（{pickedCandidates.length}）
                  </Button>
                </Group>
              </div>
              {candOpen && (
              <div
                className="jt-panel-body"
                style={{ maxHeight: "55vh", overflowY: "auto" }}
              >
                <Stack gap={8}>
                  <Group gap={10} wrap="nowrap">
                    <Checkbox
                      checked={allPicked}
                      indeterminate={somePicked}
                      onChange={toggleAll}
                    />
                    <Text fz="xs" c="dimmed">
                      全選（{pickedCandidates.length}/{candidates.length}）
                    </Text>
                  </Group>
                  {candidates.map((c) => (
                    <Group key={c.job.job_id} gap={10} wrap="nowrap">
                      <Checkbox
                        checked={picked.has(c.job.job_id)}
                        onChange={() => toggle(c.job.job_id)}
                      />
                      <a className="jt-job-title" href={c.job.url} target="_blank" rel="noreferrer"
                         style={{ flex: 1 }}>{c.job.title}</a>
                      <Text fz="xs" c="dimmed">{c.job.company}</Text>
                      {c.job.salary && <Text fz="xs" c="dimmed">{c.job.salary}</Text>}
                      {!c.relevant && (
                        <span className="jt-chip" style={{ color: "var(--jt-dim)" }}>廣告？</span>
                      )}
                    </Group>
                  ))}
                </Stack>
              </div>
              )}
            </div>
          )}

          {/* 結果 */}
          <div className="jt-panel">
            <div className="jt-panel-head">
              <span className="jt-eyebrow">
                分析結果 // RANKED
                {results.length ? (
                  <>
                    {" · "}
                    <b>{results.length}</b> 筆
                  </>
                ) : null}
              </span>
            </div>
            <div
              className="jt-panel-body"
              data-center={!results.length && !busy}
            >
              {matchesQ.isLoading ? (
                <div className="jt-empty">載入中…</div>
              ) : results.length ? (
                <Stack gap={12}>
                  {results.slice(0, resultLimit).map((m) =>
                    m.status === "done" ? (
                      <MatchCard key={m.job.job_id} match={m} searchId={selectedId!} />
                    ) : m.status === "failed" ? (
                      <div key={m.job.job_id} className="jt-jobcard">
                        <Group justify="space-between">
                          <div>
                            <div className="jt-job-title">{m.job.title}</div>
                            <div className="jt-job-meta">{m.job.company} · 分析失敗</div>
                          </div>
                          <Button size="xs" variant="default"
                                  onClick={() => api.analyzeSelected(selectedId!, [m.job.job_id])
                                    .then(() => qc.invalidateQueries({ queryKey: ["search-matches", selectedId] }))}>
                            重試
                          </Button>
                        </Group>
                      </div>
                    ) : (
                      <div key={m.job.job_id} className="jt-jobcard">
                        <Group gap={10}>
                          <Loader size="xs" color="teal" />
                          <div>
                            <div className="jt-job-title">{m.job.title}</div>
                            <div className="jt-job-meta">{m.job.company} · 分析中…</div>
                          </div>
                        </Group>
                      </div>
                    )
                  )}
                  {results.length > resultLimit && (
                    <Button variant="default" size="xs"
                            onClick={() => setResultLimit((l) => l + 12)}>
                      顯示更多（還有 {results.length - resultLimit} 筆）
                    </Button>
                  )}
                </Stack>
              ) : crawlStatus === "queued" || crawlStatus === "crawling" ? (
                <div className="jt-empty">
                  {agentQ.data?.online ? "爬取中…請稍候" : "排隊中 · 等爬蟲上線"}
                </div>
              ) : crawlStatus === "expired" ? (
                <div className="jt-empty">已過期 · 請重新搜尋</div>
              ) : (
                <div className="jt-empty">
                  尚無結果 // 輸入關鍵字後執行「爬取候選」，勾選後「分析選中」
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </Box>
  );
}

function MatchCard({ match, searchId }: { match: JobMatch; searchId: string }) {
  const { job, score, reasons, gaps, requires_external_apply } = match;
  const benefits = match.benefits ?? [];
  const qc = useQueryClient();
  const [opened, { open, close }] = useDisclosure(false);
  // 已存的求職信當作初始內容（重開直接看，不必重生）
  const [draft, setDraft] = useState(match.cover_letter ?? "");
  const [expanded, setExpanded] = useState(false);
  const hasLetter = !!draft;

  const letterMut = useMutation({
    mutationFn: api.coverLetter,
    onSuccess: (d) => {
      setDraft(d.cover_letter);
      qc.invalidateQueries({ queryKey: ["search-matches", searchId] });
      qc.invalidateQueries({ queryKey: ["quota"] });
      qc.invalidateQueries({ queryKey: ["usage"] });
      qc.invalidateQueries({ queryKey: ["usage-global"] });
    },
  });

  const generate = () => {
    letterMut.mutate({ search_id: searchId, job_id: job.job_id });
  };
  const openLetter = () => {
    open();
    if (!draft && !letterMut.isPending) generate();
  };

  const appsQ = useQuery({ queryKey: ["applications"], queryFn: api.listApplications });
  const tracked = (appsQ.data ?? []).some((a) => a.job_id === job.job_id);

  const trackMut = useMutation({
    mutationFn: () => api.addApplication({ search_id: searchId, job_id: job.job_id }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["applications"] }),
  });

  // 生成中的經過秒數（讓使用者知道在跑、別關視窗）
  const [, setTick] = useState(0);
  useEffect(() => {
    if (!letterMut.isPending) return;
    const id = setInterval(() => setTick((t) => t + 1), 1000);
    return () => clearInterval(id);
  }, [letterMut.isPending]);
  const elapsed = letterMut.submittedAt
    ? Math.max(0, Math.floor((Date.now() - letterMut.submittedAt) / 1000))
    : 0;

  return (
    <div className="jt-jobcard">
      <div className="jt-job-head">
        <div>
          <a className="jt-job-title" href={job.url} target="_blank" rel="noreferrer">
            {job.title}
          </a>
          <div className="jt-job-meta">
            {job.company}
            {job.salary ? ` · ${job.salary}` : ""}
          </div>
        </div>
        <div className="jt-score">
          <b>{score}</b>
          <small>match</small>
        </div>
      </div>

      {benefits.length > 0 && (
        <Group gap={6}>
          {benefits.map((b, i) => (
            <span key={`b${i}`} className="jt-chip jt-chip--teal">
              {b}
            </span>
          ))}
        </Group>
      )}

      {expanded && (
        <>
          <div className="jt-meter">
            <span style={{ width: `${Math.max(0, Math.min(100, score))}%` }} />
          </div>

          <div className="jt-tags">
            {reasons.map((r, i) => (
              <div key={`r${i}`} className="jt-tag" data-kind="pos">
                <span className="m">[+]</span>
                <span>{r}</span>
              </div>
            ))}
            {gaps.map((g, i) => (
              <div key={`g${i}`} className="jt-tag" data-kind="neg">
                <span className="m">[!]</span>
                <span>{g}</span>
              </div>
            ))}
          </div>

          {(requires_external_apply || hasLetter) && (
            <Group gap={8}>
              {requires_external_apply && (
                <span className="jt-chip">⚑ 需至官網投遞</span>
              )}
              {hasLetter && (
                <span className="jt-chip jt-chip--teal">
                  ✎ 已寫求職信
                </span>
              )}
            </Group>
          )}
          <div style={{ borderTop: "1px solid var(--jt-border)", marginTop: 2 }} />
          <Group justify="flex-end" gap={8}>
            <Button
              size="xs"
              variant="light"
              color="teal"
              disabled={tracked || trackMut.isPending}
              loading={trackMut.isPending}
              onClick={() => trackMut.mutate()}
            >
              {tracked ? "✓ 已在追蹤清單" : "☆ 加入追蹤"}
            </Button>
            <Button size="xs" variant="default" onClick={openLetter}>
              {hasLetter ? "查看求職信" : "生成求職信"}
            </Button>
          </Group>
        </>
      )}

      <Group justify="center" mt={2}>
        <Button size="xs" variant="subtle" color="gray"
                onClick={() => setExpanded((e) => !e)}>
          {expanded ? "▴ 收合" : "▾ 展開"}
        </Button>
      </Group>

      <Modal
        opened={opened}
        onClose={close}
        size="lg"
        closeOnClickOutside={!letterMut.isPending}
        closeOnEscape={!letterMut.isPending}
        title={
          <span className="jt-eyebrow">
            求職信 // {job.company} · {job.title}
          </span>
        }
      >
        {letterMut.isPending ? (
          <Stack align="center" py={40} gap={10}>
            <Loader size="sm" color="tangerine" />
            <Text fz="sm" c="dimmed" ta="center">
              生成中…約需 20–40 秒，請勿關閉視窗（{elapsed}s）
            </Text>
          </Stack>
        ) : letterMut.isError ? (
          <Text fz="sm" c="tangerine.5">
            生成失敗，請重試。
          </Text>
        ) : (
          <Stack gap={12}>
            <Textarea
              autosize
              minRows={12}
              maxRows={24}
              value={draft}
              onChange={(e) => setDraft(e.currentTarget.value)}
              styles={{
                input: { fontFamily: "var(--mantine-font-family-monospace)" },
              }}
            />
            <Group justify="flex-end">
              <Button
                variant="light"
                color="teal"
                disabled={tracked || trackMut.isPending}
                onClick={() => trackMut.mutate()}
              >
                {tracked ? "✓ 已在追蹤清單" : "加入追蹤"}
              </Button>
              <Button variant="subtle" color="gray" onClick={generate}>
                重新生成
              </Button>
              <CopyButton value={draft}>
                {({ copied, copy }) => (
                  <Button color="tangerine" onClick={copy}>
                    {copied ? "已複製" : "複製"}
                  </Button>
                )}
              </CopyButton>
            </Group>
          </Stack>
        )}
      </Modal>
    </div>
  );
}
