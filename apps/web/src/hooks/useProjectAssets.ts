/**
 * useProjectAssets — manages the founder's attached assets for a project.
 *
 * Owns:
 *   - the current list of assets (status, name, digest_tokens)
 *   - upload(file)       — POSTs to the API and adds the row to local state
 *   - remove(assetId)    — soft-delete
 *   - background polling — every 4s while any asset is pending/processing,
 *                          so the founder sees the status flip to 'ready'
 *                          without manual refresh
 *
 * Maya doesn't need to read this surface — she reads digests server-side
 * via the context layer. This hook is purely for the UI (chips, settings).
 */
import { useCallback, useEffect, useRef, useState } from "react";
import {
  apiListAssets,
  apiUploadAsset,
  apiDeleteAsset,
  type ProjectAsset,
} from "@/lib/api";

const POLL_MS = 4000;

// Mirror of MAX_UPLOAD_BYTES in apps/api/app/routes/assets.py. Kept as a
// constant so when we ever raise the cap, only one place needs to change
// and the user-facing label here stays in sync.
const MAX_UPLOAD_BYTES = 10 * 1024 * 1024;
const MAX_UPLOAD_BYTES_LABEL = "10 MB";

export function useProjectAssets(projectId: string | null) {
  const [assets, setAssets] = useState<ProjectAsset[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<number | null>(null);

  const refresh = useCallback(async () => {
    if (!projectId) return;
    try {
      const { assets } = await apiListAssets(projectId);
      setAssets(assets);
      setError(null);
    } catch (e: any) {
      // Tolerate 404 (old API version without asset routes) — render empty
      // rather than show a perma-error banner. Real failures (auth, 500)
      // still surface.
      const msg = e?.message ?? String(e);
      if (typeof msg === "string" && /404|Not Found/i.test(msg)) {
        setAssets([]);
        setError(null);
        return;
      }
      setError(msg);
    }
  }, [projectId]);

  const upload = useCallback(
    async (file: File) => {
      if (!projectId) return null;
      // Frontend pre-check: reject obviously-too-large files instantly so
      // the founder isn't waiting for the bytes to traverse the wire.
      // Backend mirror cap is in apps/api/app/routes/assets.py (MAX_UPLOAD_BYTES).
      if (file.size > MAX_UPLOAD_BYTES) {
        const mb = (file.size / (1024 * 1024)).toFixed(1);
        setError(
          `"${file.name}" is ${mb} MB — max is ${MAX_UPLOAD_BYTES_LABEL}. Try a smaller file or compress it first.`,
        );
        return null;
      }
      setLoading(true);
      setError(null);
      try {
        const asset = await apiUploadAsset(projectId, file);
        // Optimistically add to local state; polling will reconcile.
        setAssets((prev) => [asset, ...prev]);
        return asset;
      } catch (e: any) {
        setError(e.message ?? String(e));
        return null;
      } finally {
        setLoading(false);
      }
    },
    [projectId],
  );

  // Founder-clearable error: ChatPanel's "×" on the error chip calls this.
  const clearError = useCallback(() => setError(null), []);

  const remove = useCallback(
    async (assetId: string) => {
      if (!projectId) return;
      try {
        await apiDeleteAsset(projectId, assetId);
        setAssets((prev) => prev.filter((a) => a.id !== assetId));
      } catch (e: any) {
        setError(e.message ?? String(e));
      }
    },
    [projectId],
  );

  // Initial fetch on project change
  useEffect(() => {
    if (!projectId) {
      setAssets([]);
      return;
    }
    refresh();
  }, [projectId, refresh]);

  // Poll while anything's in-flight
  useEffect(() => {
    const inFlight = assets.some(
      (a) => a.status === "pending" || a.status === "processing",
    );
    if (!inFlight || !projectId) {
      if (pollRef.current) {
        window.clearInterval(pollRef.current);
        pollRef.current = null;
      }
      return;
    }
    if (pollRef.current) return; // already polling
    pollRef.current = window.setInterval(refresh, POLL_MS);
    return () => {
      if (pollRef.current) {
        window.clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [assets, projectId, refresh]);

  return { assets, loading, error, clearError, upload, remove, refresh };
}
