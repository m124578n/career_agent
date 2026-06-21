import { useState } from "react";
import { Button, FileInput, NumberInput, Stack, TextInput, Title } from "@mantine/core";

// M1：上傳履歷 + 設定目標職位/薪資。骨架，待串 api.parseResume。
export function ResumeSetup() {
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [salary, setSalary] = useState<number | string>("");

  return (
    <Stack maw={480}>
      <Title order={3}>履歷與目標設定</Title>
      <FileInput
        label="履歷檔（PDF / DOCX / TXT）"
        placeholder="選擇檔案"
        value={file}
        onChange={setFile}
      />
      <TextInput
        label="目標職位"
        value={title}
        onChange={(e) => setTitle(e.currentTarget.value)}
      />
      <NumberInput label="期望月薪（TWD）" value={salary} onChange={setSalary} />
      <Button disabled={!file || !title}>儲存並診斷</Button>
    </Stack>
  );
}
