import { GoogleLogin } from "@react-oauth/google";
import { useAuth } from "../state/auth";

export function LoginScreen() {
  const { login } = useAuth();
  return (
    <div
      style={{
        minHeight: "100dvh",
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
        <p style={{ color: "var(--jt-muted)", fontSize: 14, margin: "22px 0 20px" }}>
          用 Google 登入開始使用。
          <br />
          履歷診斷、職缺契合度、求職信 —— 每日有使用額度。
        </p>
        <div style={{ display: "flex", justifyContent: "center" }}>
          <GoogleLogin
            onSuccess={(r) => r.credential && login(r.credential)}
            onError={() => undefined}
            theme="filled_black"
            shape="pill"
          />
        </div>
      </div>
    </div>
  );
}
