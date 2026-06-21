import {
  Box,
  Button,
  CopyButton,
  Group,
  Loader,
  Modal,
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
import { AnalyzingSteps } from "../components/AnalyzingSteps";
import type { JobMatch } from "../types";

export function JobList() {
  const { target } = useResume();
  const [keyword, setKeyword] = useState("");
  const qc = useQueryClient();

  const [offset, setOffset] = useState(0);
  const [noMore, setNoMore] = useState(false);

  const matchesQ = useQuery({ queryKey: ["matches"], queryFn: api.listMatches });
  const analyzeMut = useMutation({
    mutationFn: api.analyzeJobs,
    onSuccess: (data, vars) => {
      setOffset((vars.offset ?? 0) + data.length);
      setNoMore(data.length === 0);
      qc.invalidateQueries({ queryKey: ["matches"] });
    },
  });

  const canRun = !!target && keyword.trim().length > 0 && !analyzeMut.isPending;
  const doAnalyze = (off: number) =>
    target &&
    analyzeMut.mutate({ keyword: keyword.trim(), target, offset: off, limit: 5 });
  const run = () => {
    setNoMore(false);
    doAnalyze(0); // 新搜尋 → 從頭
  };
  const runNext = () => doAnalyze(offset); // 翻下一批

  const matches = matchesQ.data ?? [];

  return (
    <Box p={{ base: "lg", md: 40 }} maw={1180} mx="auto">
      <Stack gap={6} mb={28}>
        <span className="jt-eyebrow">
          職缺 <b>×</b> 契合度
        </span>
        <Title order={1} fz={{ base: 28, md: 34 }} fw={700} lts="-0.02em">
          職缺契合度
        </Title>
        <Text c="dimmed" fz="sm" maw={580}>
          輸入關鍵字爬取 104 職缺，逐筆比對你的履歷並排序。每次分析前 5 筆（含節流，需稍候）。
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
              <Group align="flex-end" gap={12} wrap="nowrap">
                <TextInput
                  label="搜尋關鍵字"
                  placeholder="例：Python 後端 / AI 工程師"
                  value={keyword}
                  onChange={(e) => setKeyword(e.currentTarget.value)}
                  onKeyDown={(e) => e.key === "Enter" && canRun && run()}
                  style={{ flex: 1 }}
                />
                <Button
                  color="tangerine"
                  size="md"
                  disabled={!canRun}
                  loading={analyzeMut.isPending}
                  onClick={run}
                >
                  爬取並分析
                </Button>
              </Group>
              <Text fz="xs" c="dimmed" mt={8}>
                目標：{target.target_title}
                {target.expected_salary
                  ? ` · 期望 ${target.expected_salary.toLocaleString()}`
                  : ""}
              </Text>
              {analyzeMut.isError && (
                <Text fz="xs" c="tangerine.5" mt={6}>
                  分析失敗：請確認後端與關鍵字後再試。
                </Text>
              )}
            </div>
          </div>

          {/* 結果 */}
          <div className="jt-panel">
            <div className="jt-panel-head">
              <span className="jt-eyebrow">
                排序結果 // RANKED
                {matches.length ? (
                  <>
                    {" · "}
                    <b>{matches.length}</b> 筆
                  </>
                ) : null}
              </span>
            </div>
            <div
              className="jt-panel-body"
              data-center={!matches.length && !analyzeMut.isPending}
            >
              {analyzeMut.isPending ? (
                <AnalyzingSteps
                  steps={[
                    "爬取 104 職缺…",
                    "讀取職缺詳情（含節流）…",
                    "逐筆比對契合度…",
                    "排序與整理結果…",
                  ]}
                />
              ) : matchesQ.isLoading ? (
                <div className="jt-empty">載入中…</div>
              ) : matches.length ? (
                <Stack gap={12}>
                  {matches.map((m) => (
                    <MatchCard key={m.job.job_id} match={m} />
                  ))}
                  {/* 翻下一批（分析過至少一批後才出現） */}
                  {offset > 0 && (
                    <Group justify="center" mt={6}>
                      {noMore ? (
                        <Text fz="xs" c="dimmed">
                          沒有更多職缺了
                        </Text>
                      ) : (
                        <Button
                          variant="default"
                          size="sm"
                          disabled={!canRun}
                          onClick={runNext}
                        >
                          分析下一批（第 {offset + 1}–{offset + 5} 筆）
                        </Button>
                      )}
                    </Group>
                  )}
                </Stack>
              ) : (
                <div className="jt-empty">
                  尚無結果 // 輸入關鍵字後執行「爬取並分析」
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </Box>
  );
}

function MatchCard({ match }: { match: JobMatch }) {
  const { job, score, reasons, gaps, requires_external_apply } = match;
  const { target } = useResume();
  const qc = useQueryClient();
  const [opened, { open, close }] = useDisclosure(false);
  // 已存的求職信當作初始內容（重開直接看，不必重生）
  const [draft, setDraft] = useState(match.cover_letter ?? "");
  const hasLetter = !!draft;

  const letterMut = useMutation({
    mutationFn: api.coverLetter,
    onSuccess: (d) => {
      setDraft(d.cover_letter);
      qc.invalidateQueries({ queryKey: ["matches"] }); // 讓清單反映「已寫」
    },
  });

  const generate = () => {
    if (target) letterMut.mutate({ target, job_id: job.job_id });
  };
  const openLetter = () => {
    open();
    if (!draft && !letterMut.isPending) generate();
  };

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
