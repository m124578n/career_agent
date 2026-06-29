import { Tabs } from "@mantine/core";
import Dashboard from "./Dashboard";
import ResumePage from "./ResumePage";

export default function App() {
  return (
    <Tabs defaultValue="dashboard" keepMounted={false} pt="sm">
      <Tabs.List px="md">
        <Tabs.Tab value="dashboard">儀表板</Tabs.Tab>
        <Tabs.Tab value="resume">履歷健檢</Tabs.Tab>
      </Tabs.List>
      <Tabs.Panel value="dashboard"><Dashboard /></Tabs.Panel>
      <Tabs.Panel value="resume"><ResumePage /></Tabs.Panel>
    </Tabs>
  );
}
