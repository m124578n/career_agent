import { Loader, Table, Text, Title } from "@mantine/core";
import { useJobs } from "../hooks/useJobs";

// M4：職缺清單 + 契合度排序。骨架，後端回傳後渲染表格。
export function JobList() {
  const { data, isLoading, error } = useJobs();

  if (isLoading) return <Loader />;
  if (error) return <Text c="red">載入失敗：{String(error)}</Text>;

  return (
    <>
      <Title order={3} mb="md">
        職缺契合度
      </Title>
      {!data?.length ? (
        <Text c="dimmed">尚無職缺。先在「履歷與目標」設定後開始爬取。</Text>
      ) : (
        <Table>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>職缺</Table.Th>
              <Table.Th>公司</Table.Th>
              <Table.Th>契合度</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody />
        </Table>
      )}
    </>
  );
}
