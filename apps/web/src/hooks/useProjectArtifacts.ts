/**
 * useProjectArtifacts — fetches PRD / sprints / tasks / decisions / discovery
 * for a project, plus a refetch trigger that fires on Maya SSE events.
 *
 * The field name `discovery` (previously `research`) reflects the renamed
 * Discovery tab; the underlying API is `apiListDiscovery`.
 */
import { useCallback, useEffect, useState } from "react";
import {
  apiGetPrd,
  apiListSprints,
  apiListTasks,
  apiListDecisions,
  apiListDiscovery,
  apiListSolutions,
  apiListFeatures,
  apiListReviews,
  type Prd,
  type Sprint,
  type Task,
  type Decision,
  type DiscoveryArtifact,
  type Solution,
  type Feature,
  type ReviewItem,
} from "@/lib/api";

/** The right-panel surfaces a Maya artifact_hint can target. Mirrors the
 *  ArtifactHint union in useMayaSession. */
export type RefreshKind =
  | "prd"
  | "sprint"
  | "decisions"
  | "discovery"
  | "solutions"
  | "features"
  | "reviews";

export interface ProjectArtifacts {
  prd: Prd | null;
  sprints: Sprint[];
  tasks: Task[];
  decisions: Decision[];
  discovery: DiscoveryArtifact[];
  solutions: Solution[];
  features: Feature[];
  reviews: ReviewItem[];
  loading: boolean;
  refresh: () => Promise<void>;
  refreshOne: (kind: RefreshKind) => Promise<void>;
  /** Merge a discovery artifact delta directly into local state — bypasses
   *  the refetch round-trip that hit a PostgREST race when Maya pinned
   *  fresh artifacts. Backend now emits the inline row on every mutation;
   *  we trust it. */
  mergeArtifact: (op: "upsert" | "delete", artifactId: string, artifact?: DiscoveryArtifact) => void;
  /** Merge a single decision delta (insert / replace by id). Same
   *  rationale as mergeArtifact — kills the race that made newly-logged
   *  decisions invisible until reload. */
  mergeDecision: (op: "upsert" | "delete", decisionId: string, decision?: Decision) => void;
  /** Bulk-upsert decisions — used when commit_guardrails fans out N rows
   *  in a single backend event. Each row is upserted by id. */
  mergeDecisionsBatch: (decisions: Decision[]) => void;
  /** Latest non-fatal refresh failure. The dashboard surfaces this so
   *  the founder knows their pinned card / new decision might not be
   *  visible because the refetch failed. Null when last refresh succeeded. */
  refreshError: string | null;
}

export function useProjectArtifacts(projectId: string | null): ProjectArtifacts {
  const [prd, setPrd] = useState<Prd | null>(null);
  const [sprints, setSprints] = useState<Sprint[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [decisions, setDecisions] = useState<Decision[]>([]);
  const [discovery, setDiscovery] = useState<DiscoveryArtifact[]>([]);
  const [solutions, setSolutions] = useState<Solution[]>([]);
  const [features, setFeatures] = useState<Feature[]>([]);
  const [reviews, setReviews] = useState<ReviewItem[]>([]);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    try {
      const [p, s, t, d, r, sol, feat, rev] = await Promise.allSettled([
        apiGetPrd(projectId),
        apiListSprints(projectId),
        apiListTasks(projectId),
        apiListDecisions(projectId),
        apiListDiscovery(projectId),
        apiListSolutions(projectId),
        apiListFeatures(projectId),
        apiListReviews(projectId),
      ]);
      if (p.status === "fulfilled") setPrd(p.value.prd);
      if (s.status === "fulfilled") setSprints(s.value.sprints);
      if (t.status === "fulfilled") setTasks(t.value.tasks);
      if (d.status === "fulfilled") setDecisions(d.value.decisions);
      if (r.status === "fulfilled") setDiscovery(r.value.discovery);
      if (sol.status === "fulfilled") setSolutions(sol.value.solutions);
      if (feat.status === "fulfilled") setFeatures(feat.value.features);
      if (rev.status === "fulfilled") setReviews(rev.value.reviews);
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  const [refreshError, setRefreshError] = useState<string | null>(null);

  const refreshOne = useCallback(
    async (kind: RefreshKind) => {
      if (!projectId) return;
      try {
        if (kind === "prd") {
          const { prd } = await apiGetPrd(projectId);
          setPrd(prd);
          // PRD update can also produce new decisions (guardrails) — refresh both
          const { decisions } = await apiListDecisions(projectId);
          setDecisions(decisions);
        } else if (kind === "sprint") {
          const [{ sprints }, { tasks }] = await Promise.all([
            apiListSprints(projectId),
            apiListTasks(projectId),
          ]);
          setSprints(sprints);
          setTasks(tasks);
        } else if (kind === "decisions") {
          const { decisions } = await apiListDecisions(projectId);
          setDecisions(decisions);
        } else if (kind === "discovery") {
          const { discovery } = await apiListDiscovery(projectId);
          setDiscovery(discovery);
        } else if (kind === "solutions") {
          const { solutions } = await apiListSolutions(projectId);
          setSolutions(solutions);
        } else if (kind === "features") {
          // The MVP cut flips in_mvp on features; that's also when reviews
          // commonly appear, so refresh both surfaces together.
          const [{ features }, { reviews }] = await Promise.all([
            apiListFeatures(projectId),
            apiListReviews(projectId),
          ]);
          setFeatures(features);
          setReviews(reviews);
        } else if (kind === "reviews") {
          const { reviews } = await apiListReviews(projectId);
          setReviews(reviews);
        }
        setRefreshError(null);
      } catch (e: any) {
        // Don't silently swallow — surface so the founder knows the
        // dashboard might be out of date and can refresh manually.
        const msg = e?.message ?? String(e);
        console.warn(`[useProjectArtifacts] refreshOne(${kind}) failed:`, msg);
        setRefreshError(`Couldn't refresh ${kind} — ${msg}`);
      }
    },
    [projectId],
  );

  useEffect(() => {
    if (!projectId) {
      setPrd(null);
      setSprints([]);
      setTasks([]);
      setDecisions([]);
      setDiscovery([]);
      setSolutions([]);
      setFeatures([]);
      setReviews([]);
      return;
    }
    refresh();
  }, [projectId, refresh]);

  const mergeArtifact = useCallback(
    (op: "upsert" | "delete", artifactId: string, artifact?: DiscoveryArtifact) => {
      setDiscovery((prev) => {
        if (op === "delete") {
          return prev.filter((r) => r.id !== artifactId);
        }
        // upsert
        if (!artifact) return prev;
        const idx = prev.findIndex((r) => r.id === artifactId);
        if (idx === -1) {
          // New row — prepend (Discovery tab orders newest-first within each stage)
          return [artifact, ...prev];
        }
        // Existing row — replace in place
        const next = prev.slice();
        next[idx] = artifact;
        return next;
      });
    },
    [],
  );

  const mergeDecision = useCallback(
    (op: "upsert" | "delete", decisionId: string, decision?: Decision) => {
      setDecisions((prev) => {
        if (op === "delete") {
          return prev.filter((d) => d.id !== decisionId);
        }
        if (!decision) return prev;
        const idx = prev.findIndex((d) => d.id === decisionId);
        if (idx === -1) {
          // List is server-ordered created_at DESC, so prepend new rows.
          return [decision, ...prev];
        }
        const next = prev.slice();
        next[idx] = decision;
        return next;
      });
    },
    [],
  );

  const mergeDecisionsBatch = useCallback((batch: Decision[]) => {
    if (batch.length === 0) return;
    setDecisions((prev) => {
      // Build a single pass: index existing by id, replace or prepend.
      const byId = new Map(prev.map((d) => [d.id, d] as const));
      const newcomers: Decision[] = [];
      for (const d of batch) {
        if (byId.has(d.id)) {
          byId.set(d.id, d);
        } else {
          newcomers.push(d);
        }
      }
      // Preserve original prev ordering for existing rows; prepend
      // newcomers (newest-first surface convention).
      const updatedExisting = prev.map((d) => byId.get(d.id) ?? d);
      return [...newcomers, ...updatedExisting];
    });
  }, []);

  return {
    prd, sprints, tasks, decisions, discovery,
    solutions, features, reviews, loading,
    refresh, refreshOne,
    mergeArtifact,
    mergeDecision,
    mergeDecisionsBatch,
    refreshError,
  };
}
