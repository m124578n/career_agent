import { Box, Stack, Text, Title } from "@mantine/core";
import { useJobs } from "../hooks/useJobs";

// M4：職缺清單 + 契合度排序。骨架，待爬蟲/分析端點串上後填入表格。
export function JobList() {
  const { data, isLoading } = useJobs();
  const count = Array.isArray(data) ? data.length : 0;

  return (
    <Box p={{ base: "lg", md: 40 }} maw={1180} mx="auto">
      <Stack gap={6} mb={32}>
        <span className="jt-eyebrow">
          職缺 <b>×</b> 契合度
        </span>
        <Title order={1} fz={{ base: 28, md: 34 }} fw={700} lts="-0.02em">
          職缺契合度
        </Title>
        <Text c="dimmed" fz="sm" maw={560}>
          依關鍵字爬取 104 職缺，逐筆比對你的履歷並排序。
        </Text>
      </Stack>

      <div className="jt-panel">
        <div className="jt-panel-head">
          <span className="jt-eyebrow">
            清單 // JOBS{count ? <> · <b>{count}</b> 筆</> : null}
          </span>
        </div>
        <div className="jt-panel-body">
          <div className="jt-empty">
            {isLoading
              ? "載入中…"
              : "尚無職缺 // 待爬取與契合度分析端點串接後顯示"}
          </div>
        </div>
      </div>
    </Box>
  );
}
