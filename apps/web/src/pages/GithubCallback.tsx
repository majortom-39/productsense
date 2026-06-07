/**
 * GitHub OAuth callback handler.
 *
 * GitHub redirects here with `?code=...&state=...`. We verify the state
 * against the one we stored in sessionStorage before redirecting to
 * GitHub, then POST the code to the API to complete the exchange.
 * On success we go back to Settings.
 */
import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Loader2, CheckCircle2, AlertTriangle } from "lucide-react";
import { apiGithubExchange } from "@/lib/api";

export default function GithubCallback() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const [status, setStatus] = useState<"working" | "done" | "error">("working");
  const [message, setMessage] = useState<string>("Completing GitHub connection…");

  useEffect(() => {
    const code = params.get("code");
    const state = params.get("state");
    const errorParam = params.get("error_description") ?? params.get("error");

    if (errorParam) {
      setStatus("error");
      setMessage(errorParam);
      return;
    }
    if (!code) {
      setStatus("error");
      setMessage("Missing authorization code in callback URL.");
      return;
    }

    const expected = sessionStorage.getItem("github_oauth_state");
    if (expected && state && expected !== state) {
      setStatus("error");
      setMessage("OAuth state mismatch — request may have been tampered with.");
      return;
    }

    (async () => {
      try {
        const { connection } = await apiGithubExchange(code);
        sessionStorage.removeItem("github_oauth_state");
        setMessage(`Connected as ${connection.github_user_login}.`);
        setStatus("done");
        // Bounce back to Settings after a beat
        setTimeout(() => navigate("/settings", { replace: true }), 1200);
      } catch (e: any) {
        setStatus("error");
        setMessage(e.message ?? "Connection failed.");
      }
    })();
  }, [params, navigate]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-background dot-bg">
      <div className="max-w-md text-center px-6">
        {status === "working" && (
          <>
            <Loader2 className="mx-auto text-muted-foreground animate-spin" size={28} />
            <p className="mt-4 text-[14px] text-foreground">{message}</p>
          </>
        )}
        {status === "done" && (
          <>
            <CheckCircle2 className="mx-auto text-emerald-600" size={28} />
            <p className="mt-4 text-[14px] text-foreground">{message}</p>
            <p className="mt-1 text-[12px] text-muted-foreground">Redirecting…</p>
          </>
        )}
        {status === "error" && (
          <>
            <AlertTriangle className="mx-auto text-rose-600" size={28} />
            <p className="mt-4 text-[14px] text-foreground font-medium">Something went wrong</p>
            <p className="mt-1 text-[12.5px] text-muted-foreground">{message}</p>
            <button
              onClick={() => navigate("/settings", { replace: true })}
              className="mt-4 px-3 py-1.5 rounded-lg bg-foreground text-background text-[12px] font-medium hover:bg-foreground/85 transition-colors"
            >
              Back to Settings
            </button>
          </>
        )}
      </div>
    </div>
  );
}
