/**
 * Shared types for ProductSense.
 *
 * These mirror the Pydantic models in apps/api. Long-term goal: auto-generate
 * this file from the Pydantic schemas. For now, kept in sync by hand.
 */

export type EntryType = 'fresh_idea';
// future: 'built_not_shipped' | 'shipped_iterating' | 'pivoting' | ...

export interface Project {
  id: string;
  userId: string;
  name: string;
  icon: string | null;
  entryType: EntryType;
  createdAt: string;
  updatedAt: string;
}

// ─── PRD ────────────────────────────────────────────────────────────────

export interface Prd {
  id: string;
  projectId: string;
  version: number;
  status: 'draft' | 'live';
  bodyMd: string | null;
  createdAt: string;
}

export interface PrdSection {
  id: string;
  prdId: string;
  sectionId: string;
  title: string;
  bodyMd: string;
  orderIndex: number;
}

// ─── Sprint + Tasks ─────────────────────────────────────────────────────

export interface Sprint {
  id: string;
  projectId: string;
  number: number;
  name: string;
  subtitle: string | null;
  status: 'active' | 'completed';
}

export type TaskStatus = 'todo' | 'in_progress' | 'done';

export interface Task {
  id: string;
  projectId: string;
  sprintId: string;
  displayId: string;
  status: TaskStatus;
  title: string;
  goal: string | null;
  description: string | null;
  acceptance: string[] | null;
  prdContext: string | null;
  doNot: string[] | null;
  blockedBy: string[] | null;
  openDecisionId: string | null;
  agentNote: string | null;
  filesTouched: string[] | null;
  completionSummary: string | null;
  buildNotes: string[] | null;
  decisionsLogged: string[] | null;
  createdAt: string;
  updatedAt: string;
}

// ─── Decisions ──────────────────────────────────────────────────────────

export type DecidedBy =
  | 'maya_autonomous'
  | 'agent_with_user'
  | 'maya_with_user'
  | 'user'
  | 'agent_flagged';

export type DecisionStatus = 'open' | 'decided';
export type DecisionOpenType = 'escalated';
export type DecisionTag = 'guardrail' | 'scope' | 'technical' | 'flagged';

export interface DecisionAffects {
  tasks?: string[];
  prdSections?: string[];
}

export interface Decision {
  id: string;
  projectId: string;
  displayId: string; // 'D-001', 'D-002', ...
  decidedBy: DecidedBy;
  status: DecisionStatus;
  openType: DecisionOpenType | null;
  title: string;
  detail: string;
  why: string;
  relatedTaskId: string | null;
  tag: DecisionTag | string | null;
  pinned: boolean;
  affects: DecisionAffects | null;
  createdAt: string;
  resolvedAt: string | null;
}

// ─── Research ───────────────────────────────────────────────────────────

export type ResearchCategory =
  | 'problem'
  | 'users'
  | 'competitors'
  | 'failure_modes'
  | 'tech';

export type ResearchStatus = 'fresh' | 'stale' | 'running';

export type ResearchTool =
  | 'iris'
  | 'aiden'
  | 'hugo'
  | 'zara'
  | 'theo';

export interface ResearchSource {
  label: string;
  url: string;
}

export interface ResearchAffects {
  tasks?: string[];
  prdSections?: string[];
  decisions?: string[];
}

export interface Research {
  id: string;
  projectId: string;
  category: ResearchCategory;
  question: string;
  status: ResearchStatus;
  finding: string | null;
  bullets: string[] | null;
  sources: ResearchSource[] | null;
  tool: ResearchTool | string;
  affects: ResearchAffects | null;
  createdAt: string;
  refreshedAt: string;
}

// ─── Chat ───────────────────────────────────────────────────────────────

export type MessageRole = 'user' | 'assistant' | 'system';

export interface ToolCall {
  name: string;
  summary: string;
}

export interface Message {
  id: string;
  projectId: string;
  role: MessageRole;
  agent: string | null;
  content: string;
  toolCall: ToolCall | null;
  quoted: string | null;
  createdAt: string;
}

// ─── Clarifications (MCP request_clarification bridge) ──────────────────

export type ClarificationStatus = 'open' | 'answered' | 'cancelled';

export interface Clarification {
  id: string;
  projectId: string;
  relatedTaskId: string;
  decisionId: string | null;
  question: string;
  status: ClarificationStatus;
  answer: string | null;
  decidedBy: DecidedBy | null;
  createdAt: string;
  resolvedAt: string | null;
}

// ─── Agent run telemetry (internal) ─────────────────────────────────────

export interface AgentRun {
  id: string;
  projectId: string | null;
  agent: string;
  invokedBy: 'founder_chat' | 'mcp' | 'cron' | 'maya' | string;
  inputSummary: string | null;
  outputSummary: string | null;
  tokensUsed: number | null;
  durationMs: number | null;
  status: 'complete' | 'budget_hit' | 'error' | string | null;
  createdAt: string;
}
