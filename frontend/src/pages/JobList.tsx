import {
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
} from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api } from "../api/client";
import { useResume } from "../state/resume";
import { REGIONS } from "../constants/regions";
import type { JobMatch } from "../types";

export function JobList() {
  const { target } = useResume();
  const [keyword, setKeyword] = useState("");
  const [area, setArea] = useState<string[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const qc = useQueryClient();

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

  const createMut = useMutation({
    mutationFn: api.createSearch,
    onSuccess: (data) => {
      setSelectedId(data.search_id);
      setPicked(new Set(data.candidates.filter((c) => c.relevant).map((c) => c.job.job_id)));
      qc.invalidateQueries({ queryKey: ["searches"] });
      qc.invalidateQueries({ queryKey: ["search-matches", data.search_id] });
    },
  });
  const crawlMut = useMutation({
    mutationFn: () => api.crawlNext(selectedId!),
    onSuccess: (data) => {
      setPicked((p) => {
        const n = new Set(p);
        data.candidates.filter((c) => c.relevant).forEach((c) => n.add(c.job.job_id));
        return n;
      });
      qc.invalidateQueries({ queryKey: ["search-matches", selectedId] });
    },
  });
  const analyzeMut = useMutation({
    mutationFn: () => api.analyzeSelected(selectedId!, [...picked]),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["search-matches", selectedId] }),
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
                  {searches.map((s) => (
                    <Group
                      key={s.search_id}
                      gap={4}
                      wrap="nowrap"
                      px={10}
                      py={6}
                      onClick={() => {
                        setSelectedId(s.search_id);
                        setPicked(new Set());
                      }}
                      style={{
                        cursor: "pointer",
                        borderRadius: 8,
                        border: "1px solid var(--jt-border)",
                        background:
                          s.search_id === selectedId
                            ? "rgba(52,214,200,0.12)"
                            : "transparent",
                      }}
                    >
                      <Text fz="xs">
                        {s.keyword} ·{" "}
                        {new Date(s.created_at).toLocaleString("zh-TW", {
                          month: "numeric",
                          day: "numeric",
                          hour: "2-digit",
                          minute: "2-digit",
                        })}{" "}
                        · {s.count} 筆
                      </Text>
                      <Text
                        fz="xs"
                        c="dimmed"
                        onClick={(e) => {
                          e.stopPropagation();
                          delMut.mutate(s.search_id);
                        }}
                        style={{ cursor: "pointer" }}
                      >
                        ✕
                      </Text>
                    </Group>
                  ))}
                </Group>
              </div>
            </div>
          )}

          {/* 候選清單 */}
          {candidates.length > 0 && (
            <div className="jt-panel" style={{ marginBottom: 20 }}>
              <div className="jt-panel-head">
                <span className="jt-eyebrow">候選 // CANDIDATES · {candidates.length}</span>
                <Group gap={8}>
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
              <div className="jt-panel-body">
                <Stack gap={8}>
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
            </div>
          )}

          {/* 結果 */}
          <div className="jt-panel">
            <div className="jt-panel-head">
              <span className="jt-eyebrow">
                排序結果 // RANKED
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
                  {results.map((m) =>
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
                </Stack>
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
  const qc = useQueryClient();
  const [opened, { open, close }] = useDisclosure(false);
  // 已存的求職信當作初始內容（重開直接看，不必重生）
  const [draft, setDraft] = useState(match.cover_letter ?? "");
  const hasLetter = !!draft;

  const letterMut = useMutation({
    mutationFn: api.coverLetter,
    onSuccess: (d) => {
      setDraft(d.cover_letter);
      qc.invalidateQueries({ queryKey: ["search-matches", searchId] });
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
          <a
            className="jt-job-title"
            href={job.url}
            target="_blank"
            rel="noreferrer"
          >
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

      <Group justify="space-between" mt={2}>
        <Group gap={8}>
          {requires_external_apply && (
            <span className="jt-chip">⚑ 需至官網投遞</span>
          )}
          {hasLetter && (
            <span className="jt-chip" style={{ color: "var(--jt-teal)", borderColor: "rgba(52,214,200,0.4)" }}>
              ✎ 已寫求職信
            </span>
          )}
        </Group>
        <Button size="xs" variant="default" onClick={openLetter}>
          {hasLetter ? "查看求職信" : "生成求職信"}
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
