import { useState } from "react";
import { Navigate } from "react-router-dom";
import { supabase } from "@/lib/supabase";
import { useAuth } from "@/context/AuthContext";

type Mode = "password" | "magic";

export default function Login() {
  const { user, loading } = useAuth();
  const [mode, setMode] = useState<Mode>("password");
  const [signupMode, setSignupMode] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  if (loading) return null;
  if (user) return <Navigate to="/" replace />;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setInfo(null);
    setSubmitting(true);

    try {
      if (mode === "magic") {
        const { error } = await supabase.auth.signInWithOtp({
          email,
          options: { emailRedirectTo: window.location.origin },
        });
        if (error) throw error;
        setSent(true);
        return;
      }

      // Password mode
      if (signupMode) {
        const { data, error } = await supabase.auth.signUp({ email, password });
        if (error) throw error;
        if (!data.session) {
          setInfo(
            "Account created — check your email to confirm. " +
              "Or, in the Supabase dashboard, disable 'Confirm email' under " +
              "Authentication → Sign In / Up to log in immediately.",
          );
        }
      } else {
        const { error } = await supabase.auth.signInWithPassword({ email, password });
        if (error) throw error;
      }
    } catch (e: any) {
      setError(e?.message || String(e));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="dot-bg min-h-screen flex items-center justify-center p-8">
      <div className="w-full max-w-sm bg-card border border-border rounded-3xl p-8">
        <img src="/Productsense_Icon Black.svg" alt="" className="h-10 w-10 mb-5" />
        <h1 className="text-xl font-semibold text-foreground mb-1 tracking-tight">
          {signupMode ? "Create your account" : "Sign in to productsense"}
        </h1>
        <p className="text-sm text-muted-foreground mb-6 leading-relaxed">
          {signupMode
            ? "Use your email and a password — Maya will be ready in a moment."
            : "Use email + password, or get a one-time link instead."}
        </p>

        {/* Mode tabs */}
        <div className="flex gap-1 bg-muted/40 rounded-xl p-1 mb-5">
          <button
            type="button"
            onClick={() => {
              setMode("password");
              setSent(false);
              setInfo(null);
              setError(null);
            }}
            className={`flex-1 px-3 py-1.5 text-xs font-medium rounded-lg transition ${
              mode === "password" ? "bg-card text-foreground shadow-sm" : "text-muted-foreground"
            }`}
          >
            Email + password
          </button>
          <button
            type="button"
            onClick={() => {
              setMode("magic");
              setSent(false);
              setInfo(null);
              setError(null);
            }}
            className={`flex-1 px-3 py-1.5 text-xs font-medium rounded-lg transition ${
              mode === "magic" ? "bg-card text-foreground shadow-sm" : "text-muted-foreground"
            }`}
          >
            Magic link
          </button>
        </div>

        {sent ? (
          <div className="text-sm text-emerald-700 bg-emerald-50 border border-emerald-100 rounded-xl px-4 py-3">
            Check your inbox for a link to <strong>{email}</strong>.
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-3">
            <input
              type="email"
              required
              autoFocus
              placeholder="you@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full px-4 py-2.5 rounded-xl border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-[#3898ec]/40"
            />
            {mode === "password" && (
              <input
                type="password"
                required
                minLength={6}
                placeholder="Password (min 6 chars)"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full px-4 py-2.5 rounded-xl border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-[#3898ec]/40"
              />
            )}
            {error && (
              <p className="text-xs text-rose-700 bg-rose-50 border border-rose-100 rounded-lg px-3 py-2">
                {error}
              </p>
            )}
            {info && (
              <p className="text-xs text-emerald-700 bg-emerald-50 border border-emerald-100 rounded-lg px-3 py-2 leading-relaxed">
                {info}
              </p>
            )}
            <button
              type="submit"
              disabled={submitting || !email || (mode === "password" && !password)}
              className="w-full py-2.5 rounded-xl bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 disabled:opacity-50 transition"
            >
              {submitting
                ? "Working…"
                : mode === "magic"
                ? "Send magic link"
                : signupMode
                ? "Create account"
                : "Sign in"}
            </button>
            {mode === "password" && (
              <button
                type="button"
                onClick={() => {
                  setSignupMode((s) => !s);
                  setError(null);
                  setInfo(null);
                }}
                className="w-full text-xs text-muted-foreground hover:text-foreground transition pt-1"
              >
                {signupMode
                  ? "Already have an account? Sign in"
                  : "Don't have an account? Sign up"}
              </button>
            )}
          </form>
        )}
      </div>
    </div>
  );
}
