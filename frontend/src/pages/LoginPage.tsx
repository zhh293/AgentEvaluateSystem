import { FormEvent, useState } from "react";
import { login, register } from "../lib/api";

export default function LoginPage({ onAuthenticated }: { onAuthenticated: () => void }) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [message, setMessage] = useState("");
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    setMessage("AUTHENTICATING…");
    try {
      const username = String(data.get("username"));
      const password = String(data.get("password"));
      if (mode === "register") await register(username, String(data.get("email")), password);
      await login(username, password);
      onAuthenticated();
    } catch (error) { setMessage(error instanceof Error ? error.message : "Authentication failed"); }
  }
  return <main className="login-page"><section className="login-card reveal"><span className="eyebrow">AGENT EVALUATION SYSTEM</span><h1>Evaluation<br /><em>control room.</em></h1><p>Authenticate to submit agents and inspect execution evidence.</p><form onSubmit={submit}><label>USERNAME<input name="username" required minLength={3} /></label>{mode === "register" && <label>EMAIL<input name="email" type="email" required /></label>}<label>PASSWORD<input name="password" type="password" required minLength={10} /></label><button className="action" type="submit">{mode === "login" ? "ENTER SYSTEM" : "CREATE ACCOUNT"} ↗</button></form><button className="text-button" onClick={() => { setMode(mode === "login" ? "register" : "login"); setMessage(""); }}>{mode === "login" ? "NEED AN ACCOUNT? REGISTER" : "ALREADY REGISTERED? SIGN IN"}</button><span className="form-state">{message}</span></section></main>;
}
