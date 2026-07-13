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
  SegmentedControl,
  Stack,
  Text,
  Textarea,
  TextInput,
  Title,
  UnstyledButton,
} from "@mantine/core";
import { IconX } from "../components/icons";
import { useDisclosure, useMediaQuery } from "@mantine/hooks";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api/client";
import { useResume } from "../state/resume";
import { REGIONS } from "../constants/regions";
import { AnalyzingSteps } from "../components/AnalyzingSteps";
import { EmptyState } from "../components/EmptyState";
import { ReadoutItem } from "../components/ReadoutItem";
import type { JobMatch } from "../types";

// 持久化搜尋狀態，切到別頁再切回來不會被清空
const KW_KEY = "jobtracker.job-keyword";
const AREA_KEY = "jobtracker.job-area";
const SEL_KEY = "jobtracker.selected-search";
const SORT_KEY = "jobtracker.job-sort";

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
  const [sortMode, setSortMode] = useState<"fit" | "recent">(() =>
    localStorage.getItem(SORT_KEY) === "recent" ? "recent" : "fit"
  );
  const [candOpen, setCandOpen] = useState(true);
  const qc = useQueryClient();
  const isMobile = useMediaQuery("(max-width: 48em)");

  // 耗額度的操作完成時主動刷新用量（取代高頻輪詢）
  const refreshUsage = () => {
    qc.invalidateQueries({ queryKey: ["quota"] });
    qc.invalidateQueries({ queryKey: ["usage"] });
    qc.invalidateQueries({ queryKey: ["usage-global"] });
  };

  const searchesQ = useQuery({ queryKey: ["searches"], queryFn: api.listSearches });

  const matchesQ = useQuery({
    queryKey: ["search-matches", selectedId],
    queryFn: () => api.searchMatches(selectedId!),
    enabled: !!selectedId,
    refetchInterval: (q) =>
      (q.state.data ?? []).some((m) => m.status === "pending") ? 2500 : false,
  });
  const matches = matchesQ.data ?? [];
  const candidates = matches.filter((m) => m.status === "candidate");
  const results = matches.filter((m) => m.status !== "candidate");

  const sortedResults = useMemo(() => {
    const arr = [...results];
    arr.sort((a, b) => {
      // pending（進行中）一律置頂；兩者皆 pending 維持原序
      const pa = a.status === "pending" ? 0 : 1;
      const pb = b.status === "pending" ? 0 : 1;
      if (pa !== pb) return pa - pb;
      if (pa === 0) return 0;
      if (sortMode === "recent") {
        // done 依 analyzed_at 由新到舊；null（含 failed / 舊資料）殿後
        const ta = a.analyzed_at ? Date.parse(a.analyzed_at) : -Infinity;
        const tb = b.analyzed_at ? Date.parse(b.analyzed_at) : -Infinity;
        if (ta !== tb) return tb - ta;
      }
      // 契合度模式，或最新模式的同層次序：分數由高到低
      return b.score - a.score;
    });
    return arr;
  }, [results, sortMode]);

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
  useEffect(() => {
    localStorage.setItem(SORT_KEY, sortMode);
  }, [sortMode]);
  // 還原的選中搜尋若已被刪除（不在歷史列表），清掉避免空白／404。
  // 僅在 searches 已落定（非重抓中）時判斷：否則剛 createSearch 後、searches 重抓
  // 尚未回來的空窗，會把剛設好的 selectedId 誤清，導致新搜尋的候選不顯示。
  useEffect(() => {
    if (
      selectedId &&
      searchesQ.data &&
      !searchesQ.isFetching &&
      !searchesQ.data.some((s) => s.search_id === selectedId)
    ) {
      setSelectedId(null);
    }
  }, [selectedId, searchesQ.data, searchesQ.isFetching]);
  // 非同步分析從「有 pending」變「全部結束」時，token 才落定 → 刷一次用量
  const hadPending = useRef(false);
  useEffect(() => {
    const has = matches.some((m) => m.status === "pending");
    if (hadPending.current && !has) refreshUsage();
    hadPending.current = has;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [matches]);

  const createMut = useMutation({
    mutationFn: api.createSearch,
    onSuccess: (data) => {
      setSelectedId(data.search_id);
      setPicked(new Set()); // 預設不勾選，讓使用者自己挑要分析的候選
      // 直接把回傳的候選 seed 進 cache，立即顯示——不靠 matchesQ 重抓（新 selectedId
      // 尚無 observer 時 invalidate 不會可靠觸發 fetch，導致候選要手動再點才出現）。
      qc.setQueryData(["search-matches", data.search_id], data.candidates);
      qc.invalidateQueries({ queryKey: ["searches"] });
    },
  });
  const crawlMut = useMutation({
    mutationFn: () => api.crawlNext(selectedId!),
    onSuccess: () => {
      // 爬下一頁不自動勾選新候選，維持使用者目前的選取
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
            <EmptyState
              title="還沒設定履歷"
              description="先到「履歷與目標」上傳履歷、填好目標職位，再回來找契合的職缺。"
              action={
                <Button component={Link} to="/resume" color="tangerine" variant="light" size="sm">
                  去設定履歷 →
                </Button>
              }
            />
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
                  搜尋職缺
                </Button>
              </Group>
              <Text fz="xs" c="dimmed" mt={8}>
                目標：{target.target_title}
                {target.expected_salary
                  ? ` · 期望 ${target.expected_salary.toLocaleString()}`
                  : ""}
              </Text>
              {(createMut.isError || crawlMut.isError) && (
                <Text fz="xs" c="danger.5" mt={6}>
                  搜尋沒成功，確認關鍵字或稍後再試一次。
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
                    "搜尋符合的職缺…",
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
              <div className="jt-panel-head" style={{ flexWrap: "wrap", rowGap: 8 }}>
                <span className="jt-eyebrow">有興趣的候選 · {candidates.length}</span>
                <Group gap={8} wrap="wrap">
                  <Button size="xs" variant="subtle" color="gray"
                          onClick={() => setCandOpen((o) => !o)}>
                    {candOpen ? "▾ 收合" : "▸ 展開"}
                  </Button>
                  <Button size={isMobile ? "sm" : "xs"} variant="default" onClick={() => crawlMut.mutate()}
                          disabled={busy} loading={crawlMut.isPending}>爬下一頁</Button>
                  <Button size={isMobile ? "sm" : "xs"} color="tangerine"
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
                    <Group key={c.job.job_id} gap={10} wrap="nowrap" align="flex-start">
                      <Checkbox
                        mt={2}
                        checked={picked.has(c.job.job_id)}
                        onChange={() => toggle(c.job.job_id)}
                      />
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <a className="jt-job-title" href={c.job.url} target="_blank" rel="noreferrer"
                           style={{ display: "block" }}>{c.job.title}</a>
                        <Group gap={8} wrap="wrap" mt={2}>
                          <Text fz="xs" c="dimmed">{c.job.company}</Text>
                          {c.job.salary && <Text fz="xs" c="dimmed">· {c.job.salary}</Text>}
                          {!c.relevant && (
                            <span className="jt-chip" style={{ color: "var(--jt-dim)" }}>廣告？</span>
                          )}
                        </Group>
                      </div>
                    </Group>
                  ))}
                </Stack>
              </div>
              )}
            </div>
          )}

          {/* 結果 */}
          <div className="jt-panel">
            <div className="jt-panel-head" style={{ flexWrap: "wrap", rowGap: 8 }}>
              <span className="jt-eyebrow">
                分析結果
                {results.length ? (
                  <>
                    {" · "}
                    <b>{results.length}</b> 筆
                  </>
                ) : null}
              </span>
              {results.length > 0 && (
                <SegmentedControl
                  size="xs"
                  value={sortMode}
                  onChange={(v) => setSortMode(v as "fit" | "recent")}
                  data={[
                    { value: "fit", label: "契合度" },
                    { value: "recent", label: "最新分析" },
                  ]}
                />
              )}
            </div>
            <div
              className="jt-panel-body"
              data-center={!results.length && !busy}
            >
              {matchesQ.isLoading ? (
                <div className="jt-empty">載入中…</div>
              ) : results.length ? (
                <Stack gap={12}>
                  {sortedResults.slice(0, resultLimit).map((m) =>
                    m.status === "done" ? (
                      <MatchCard key={m.job.job_id} match={m} searchId={selectedId!} />
                    ) : m.status === "failed" ? (
                      <div key={m.job.job_id} className="jt-jobcard">
                        <Group justify="space-between">
                          <div>
                            <div className="jt-job-title">{m.job.title}</div>
                            <div className="jt-job-meta">{m.job.company} · <span style={{ color: "var(--jt-danger)" }}>分析沒成功</span></div>
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
              ) : (
                <EmptyState
                  title="還沒有分析結果"
                  description="先搜尋職缺、勾選有興趣的候選，再按「分析選中」，我幫你逐筆比對排序。"
                />
              )}
            </div>
          </div>
        </>
      )}
    </Box>
  );
}

type FitTier = "high" | "mid" | "low";
function fitTier(score: number): FitTier {
  return score >= 80 ? "high" : score >= 60 ? "mid" : "low";
}
function fitLabel(tier: FitTier): string {
  return tier === "high" ? "很適合" : tier === "mid" ? "還不錯" : "可考慮";
}

function MatchCard({ match, searchId }: { match: JobMatch; searchId: string }) {
  const { job, score, reasons, gaps, requires_external_apply } = match;
  const benefits = match.benefits ?? [];
  const qc = useQueryClient();
  const [opened, { open, close }] = useDisclosure(false);
  const isMobile = useMediaQuery("(max-width: 48em)");
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
          <b data-fit={fitTier(score)}>{score}</b>
          <span className="jt-fitlabel" data-fit={fitTier(score)}>{fitLabel(fitTier(score))}</span>
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

          <div className="jt-readout">
            {reasons.map((r, i) => (
              <ReadoutItem key={`r${i}`} kind="pos">{r}</ReadoutItem>
            ))}
            {gaps.map((g, i) => (
              <ReadoutItem key={`g${i}`} kind="warn">{g}</ReadoutItem>
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
        fullScreen={isMobile}
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
          <Text fz="sm" c="danger.5">
            生成沒成功，請再試一次。
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
