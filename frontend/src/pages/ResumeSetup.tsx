import { useState } from "react";
import {
  Box,
  Button,
  Group,
  Loader,
  NumberInput,
  SimpleGrid,
  Stack,
  Text,
  TextInput,
  Title,
  UnstyledButton,
  FileButton,
} from "@mantine/core";
import { useMutation } from "@tanstack/react-query";
import { api } from "../api/client";

export function ResumeSetup() {
  const [file, setFile] = useState<File | null>(null);
  const [resumeText, setResumeText] = useState("");
  const [title, setTitle] = useState("");
  const [salary, setSalary] = useState<number | string>("");

  const parseMut = useMutation({
    mutationFn: api.parseResume,
    onSuccess: (d) => setResumeText(d.text),
  });
  const diagMut = useMutation({ mutationFn: api.diagnose });

  const onFile = (f: File | null) => {
    setFile(f);
    setResumeText("");
    diagMut.reset();
    if (f) parseMut.mutate(f);
  };

  const canRun = !!resumeText && title.trim().length > 0 && !diagMut.isPending;

  const run = () =>
    diagMut.mutate({
      target_title: title.trim(),
      expected_salary: typeof salary === "number" ? salary : null,
      resume_text: resumeText,
    });

  return (
    <Box p={{ base: "lg", md: 40 }} maw={1180} mx="auto">
      {/* Header */}
      <Stack gap={6} mb={32}>
        <span className="jt-eyebrow">
          履歷 <b>×</b> 目標
        </span>
        <Title order={1} fz={{ base: 28, md: 34 }} fw={700} lts="-0.02em">
          設定你的求職基準
        </Title>
        <Text c="dimmed" fz="sm" maw={560}>
          上傳履歷、設定目標職位與期望薪資，拿到一份針對「這個職位」的優勢／待補強分析。
        </Text>
      </Stack>

      <SimpleGrid cols={{ base: 1, md: 2 }} spacing={24}>
        {/* 輸入 */}
        <div className="jt-panel">
          <div className="jt-panel-head">
            <span className="jt-eyebrow">輸入 // INPUT</span>
          </div>
          <div className="jt-panel-body">
            <Stack gap={18}>
              <FileButton onChange={onFile} accept=".pdf,.docx,.txt">
                {(props) => (
                  <UnstyledButton
                    {...props}
                    className="jt-drop"
                    data-loaded={!!resumeText}
                  >
                    <Group gap={8} wrap="nowrap">
                      <Text fz="sm" fw={500} c="var(--jt-text)">
                        {file ? file.name : "選擇履歷檔"}
                      </Text>
                      {parseMut.isPending && <Loader size={14} color="teal" />}
                    </Group>
                    <Text fz="xs" c="dimmed">
                      {resumeText
                        ? `已解析 · ${resumeText.length.toLocaleString()} 字`
                        : "支援 PDF / DOCX / TXT，點擊或拖入"}
                    </Text>
                  </UnstyledButton>
                )}
              </FileButton>
              {parseMut.isError && (
                <Text fz="xs" c="tangerine.5">
                  解析失敗：請換一個檔案或確認格式。
                </Text>
              )}

              <TextInput
                label="目標職位"
                placeholder="例：資深 Python 後端工程師"
                value={title}
                onChange={(e) => setTitle(e.currentTarget.value)}
              />
              <NumberInput
                label="期望月薪（TWD）"
                placeholder="例：70000"
                value={salary}
                onChange={setSalary}
                thousandSeparator=","
                min={0}
                step={5000}
              />

              <Button
                color="tangerine"
                size="md"
                disabled={!canRun}
                loading={diagMut.isPending}
                onClick={run}
                mt={4}
              >
                執行診斷
              </Button>
            </Stack>
          </div>
        </div>

        {/* 診斷讀數 */}
        <div className="jt-panel">
          <div className="jt-panel-head">
            <span className="jt-eyebrow">
              診斷讀數 // READOUT
              {diagMut.data && (
                <>
                  {"  "}
                  <b>{diagMut.data.strengths.length} 優勢</b>
                  {" · "}
                  {diagMut.data.gaps.length} 待補強
                </>
              )}
            </span>
          </div>
          <div className="jt-panel-body" data-center={!diagMut.data}>
            {diagMut.isPending ? (
              <div className="jt-empty">
                <Loader size="sm" color="tangerine" />
                <Text mt={12} fz="sm" c="dimmed">
                  分析中 // 對標目標職位評估履歷…
                </Text>
              </div>
            ) : diagMut.isError ? (
              <div className="jt-empty">
                診斷失敗 // 請稍後再試或確認後端設定
              </div>
            ) : diagMut.data ? (
              <Diagnosis
                strengths={diagMut.data.strengths}
                gaps={diagMut.data.gaps}
              />
            ) : (
              <div className="jt-empty">
                等待輸入 // 上傳履歷並設定目標後執行診斷
              </div>
            )}
          </div>
        </div>
      </SimpleGrid>
    </Box>
  );
}

function Diagnosis({
  strengths,
  gaps,
}: {
  strengths: string[];
  gaps: string[];
}) {
  return (
    <Stack gap={22}>
      <Section label="優勢" tag="STRENGTHS" kind="pos" items={strengths} />
      <Section label="待補強" tag="GAPS" kind="neg" items={gaps} />
    </Stack>
  );
}

function Section({
  label,
  tag,
  kind,
  items,
}: {
  label: string;
  tag: string;
  kind: "pos" | "neg";
  items: string[];
}) {
  return (
    <Stack gap={10}>
      <span className="jt-eyebrow">
        {label} // {tag}
      </span>
      <div className="jt-readout">
        {items.map((text, i) => (
          <div key={i} className="jt-item" data-kind={kind}>
            <span className="jt-mark">{kind === "pos" ? "[+]" : "[!]"}</span>
            <span>{text}</span>
          </div>
        ))}
      </div>
    </Stack>
  );
}
