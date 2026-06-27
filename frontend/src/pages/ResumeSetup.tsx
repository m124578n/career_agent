import { useEffect, useState } from "react";
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
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { useResume } from "../state/resume";
import { AnalyzingSteps } from "../components/AnalyzingSteps";
import { EmptyState } from "../components/EmptyState";
import { ReadoutItem } from "../components/ReadoutItem";

export function ResumeSetup() {
  const { target, setTarget, diagnosis, setDiagnosis } = useResume();
  const [file, setFile] = useState<File | null>(null);
  // 從共用狀態還原，切到別頁再切回來不會被清空
  const [resumeText, setResumeText] = useState(target?.resume_text ?? "");
  const [title, setTitle] = useState(target?.target_title ?? "");
  const [salary, setSalary] = useState<number | string>(
    target?.expected_salary ?? ""
  );

  // 履歷與目標就緒時，存進共用狀態供「職缺契合度」頁使用
  useEffect(() => {
    if (resumeText && title.trim()) {
      setTarget({
        target_title: title.trim(),
        expected_salary: typeof salary === "number" ? salary : null,
        resume_text: resumeText,
      });
    }
  }, [resumeText, title, salary, setTarget]);

  const parseMut = useMutation({
    mutationFn: api.parseResume,
    onSuccess: (d) => setResumeText(d.text),
  });
  const diagMut = useMutation({
    mutationFn: api.diagnose,
    onSuccess: (d) => setDiagnosis(d), // 存進共用狀態，切頁回來仍在
  });

  const onFile = (f: File | null) => {
    setFile(f);
    setResumeText("");
    diagMut.reset();
    setDiagnosis(null); // 換新履歷 → 清掉舊診斷
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
      <Stack gap={6} mb={32}>
        <span className="jt-eyebrow">第 1 步</span>
        <Title order={1} fz={{ base: 28, md: 34 }} fw={700} lts="-0.02em">
          先讓我認識你
        </Title>
        <Text c="dimmed" fz="sm" maw={560}>
          上傳履歷、填好想找的職位，我就幫你看看「這個職位」上你的亮點，
          還有可以加強的地方。
        </Text>
      </Stack>

      <SimpleGrid cols={{ base: 1, md: 2 }} spacing={24}>
        {/* 輸入 */}
        <div className="jt-panel">
          <div className="jt-panel-head">
            <span className="jt-eyebrow">上傳與設定</span>
          </div>
          <div className="jt-panel-body">
            <Stack gap={18}>
              <FileButton onChange={onFile} accept=".pdf,.docx,.txt">
                {(props) => (
                  <UnstyledButton {...props} className="jt-drop" data-loaded={!!resumeText}>
                    <Group gap={8} wrap="nowrap">
                      <Text fz="sm" fw={500} c="var(--jt-text)">
                        {file ? file.name : resumeText ? "✓ 已載入履歷" : "選擇你的履歷檔"}
                      </Text>
                      {parseMut.isPending && <Loader size={14} color="teal" />}
                    </Group>
                    <Text fz="xs" c="dimmed">
                      {parseMut.isPending
                        ? "正在讀取你的履歷…"
                        : resumeText
                          ? `讀好了 · 共 ${resumeText.length.toLocaleString()} 字`
                          : "支援 PDF / DOCX / TXT，點一下或把檔案拖進來"}
                    </Text>
                  </UnstyledButton>
                )}
              </FileButton>
              {parseMut.isError && (
                <Text fz="xs" c="danger.5">
                  這個檔案讀不太到，換一個檔案或確認格式再試一次。
                </Text>
              )}

              <TextInput
                label="想找什麼職位？"
                placeholder="例：資深 Python 後端工程師"
                value={title}
                onChange={(e) => setTitle(e.currentTarget.value)}
              />
              <NumberInput
                label="期望月薪（TWD，可留空）"
                placeholder="例：70000"
                value={salary}
                onChange={setSalary}
                thousandSeparator=","
                min={0}
                step={5000}
              />

              <Button color="tangerine" size="md" disabled={!canRun} loading={diagMut.isPending} onClick={run} mt={4}>
                開始診斷
              </Button>
              <Text fz="xs" c="dimmed" ta="center">
                上傳履歷並填好職位後就能開始
              </Text>
            </Stack>
          </div>
        </div>

        <div className="jt-panel">
          <div className="jt-panel-head">
            <span className="jt-eyebrow">
              你的診斷結果
              {diagnosis && (
                <>
                  {"　"}
                  <b style={{ color: "var(--jt-teal)" }}>{diagnosis.strengths.length} 個亮點</b>
                  {" · "}
                  {diagnosis.gaps.length} 個可加強
                </>
              )}
            </span>
          </div>
          <div className="jt-panel-body" data-center={!diagnosis && !diagMut.isPending}>
            {diagMut.isPending ? (
              <AnalyzingSteps
                steps={[
                  "讀取你的履歷與目標…",
                  "對著這個職位看你的亮點…",
                  "整理可以加強的地方…",
                  "彙整成一份診斷…",
                ]}
                intervalSec={4}
              />
            ) : diagMut.isError ? (
              <EmptyState
                title="分析沒成功"
                description="先確認網路或稍後再試一次。"
                action={
                  <Button size="xs" variant="default" onClick={run}>
                    再試一次
                  </Button>
                }
              />
            ) : diagnosis ? (
              <Diagnosis strengths={diagnosis.strengths} gaps={diagnosis.gaps} />
            ) : (
              <EmptyState
                title="還沒有診斷結果"
                description="上傳履歷、填好目標職位，我就幫你看看亮點和可以加強的地方。"
              />
            )}
          </div>
        </div>
      </SimpleGrid>
    </Box>
  );
}

function Diagnosis({ strengths, gaps }: { strengths: string[]; gaps: string[] }) {
  return (
    <Stack gap={22}>
      <Section label="你的亮點" kind="pos" items={strengths} />
      <Section label="可以加強的地方" kind="warn" items={gaps} />
      <Button
        component={Link}
        to="/jobs"
        color="tangerine"
        variant="light"
        size="sm"
        mt={4}
      >
        下一步：去找職缺 →
      </Button>
    </Stack>
  );
}

function Section({
  label,
  kind,
  items,
}: {
  label: string;
  kind: "pos" | "warn";
  items: string[];
}) {
  return (
    <Stack gap={10}>
      <span className="jt-eyebrow">{label}</span>
      <div className="jt-readout">
        {items.map((text, i) => (
          <ReadoutItem key={i} kind={kind}>
            {text}
          </ReadoutItem>
        ))}
      </div>
    </Stack>
  );
}
