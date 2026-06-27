import { GoogleLogin } from "@react-oauth/google";
import { notifications } from "@mantine/notifications";
import { useAuth } from "../state/auth";
import { Footer } from "./Footer";

export function LoginScreen() {
  const { login } = useAuth();
  return (
    <div style={{ minHeight: "100dvh", display: "flex", flexDirection: "column" }}>
      <div
        style={{
          flex: 1,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          padding: 24,
        }}
      >
        <div
          className="jt-panel"
          style={{ padding: 40, maxWidth: 380, width: "100%", textAlign: "center" }}
        >
          <span className="jt-brand" style={{ fontSize: 22 }}>
            JobTracker<span className="dot">.</span>
          </span>
          <div className="jt-brandtag" style={{ marginTop: 8 }}>
            AI 求職指揮艙
          </div>
          <p style={{ color: "var(--jt-text)", fontSize: 16, fontWeight: 600, margin: "22px 0 6px" }}>
            準備好開始找下一份工作了嗎？
          </p>
          <p style={{ color: "var(--jt-muted)", fontSize: 14, margin: "0 0 20px", lineHeight: 1.6 }}>
            用 Google 登入，我陪你做履歷診斷、找契合的職缺、寫求職信。
            <br />
            每日有免費使用額度。
          </p>
          <div style={{ display: "flex", justifyContent: "center" }}>
            <GoogleLogin
              onSuccess={(r) => r.credential && login(r.credential)}
              onError={() =>
                notifications.show({
                  color: "red",
                  title: "登入失敗",
                  message: "Google 登入沒有完成，請再試一次。",
                })
              }
              theme="filled_black"
              shape="pill"
            />
          </div>
        </div>
      </div>
      <Footer />
    </div>
  );
}
