import { Tabs } from "@mantine/core";
import { useState } from "react";
import ChatPage from "./ChatPage";
import Dashboard from "./Dashboard";
import MatchPage from "./MatchPage";
import RecommendPage from "./RecommendPage";
import ResumePage from "./ResumePage";
import SearchPage from "./SearchPage";

export default function App() {
  const [tab, setTab] = useState<string | null>("dashboard");
  return (
    <Tabs value={tab} onChange={setTab} keepMounted={false} pt="sm">
      <Tabs.List px="md">
        <Tabs.Tab value="dashboard">儀表板</Tabs.Tab>
        <Tabs.Tab value="resume">履歷健檢</Tabs.Tab>
        <Tabs.Tab value="match">JD 比對</Tabs.Tab>
        <Tabs.Tab value="recommend">推薦</Tabs.Tab>
        <Tabs.Tab value="search">職缺搜尋</Tabs.Tab>
        <Tabs.Tab value="chat">整理助手</Tabs.Tab>
      </Tabs.List>
      <Tabs.Panel value="dashboard"><Dashboard onGoRecommend={() => setTab("recommend")} /></Tabs.Panel>
      <Tabs.Panel value="resume"><ResumePage /></Tabs.Panel>
      <Tabs.Panel value="match"><MatchPage /></Tabs.Panel>
      <Tabs.Panel value="recommend"><RecommendPage /></Tabs.Panel>
      <Tabs.Panel value="search"><SearchPage /></Tabs.Panel>
      <Tabs.Panel value="chat"><ChatPage /></Tabs.Panel>
    </Tabs>
  );
}
