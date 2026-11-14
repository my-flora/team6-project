/**
 * 契约类型定义 —— 与 /contracts（V1.0 冻结）及 backend/core 一一对应。
 * 修改本文件须经 ADR 评审（Owner：陈欣然）。
 */

// ---------- 唯一状态枚举 ----------

export type ProjectStatus = "RUNNING" | "PAUSED" | "FROZEN";

export type StageStatus =
  | "NOT_STARTED"
  | "IN_PROGRESS"
  | "WAITING_HUMAN"
  | "COMPLETED"
  | "REJECTED";

export type EntryStatus = "DRAFT" | "PENDING_REVIEW" | "APPROVED" | "REJECTED";

export type GateStatus = "PENDING" | "APPROVED" | "REJECTED" | "DECIDED";

export type RoundStatus = "ONGOING" | "CONVERGED" | "TERMINATED";

export type AgentRole = "PM" | "BA" | "UX" | "TECH" | "ARCH" | "RED_TEAM" | "FORMATTER";

export type Stage =
  | "IDEA"
  | "DISCUSSION"
  | "PROPOSAL"
  | "EVALUATION"
  | "REQUIREMENT"
  | "CONFIRMATION";

export const MAX_ROUNDS = 5;

// ---------- 契约请求体 ----------

/** AgentMessageRequest（contracts/agent-message.schema.json） */
export interface AgentMessageRequest {
  project_id: string;
  stage: Stage;
  agent_role: AgentRole;
  topic_id?: string;
  round_no?: number; // 1-5
  content: string;
  /** 引用的黑板条目 ID；为空将被 /gate/messages/validate 拒收（E002） */
  references: string[];
}

/** StageAdvanceRequest（contracts/stage-advance.schema.json） */
export interface StageAdvanceRequest {
  project_id: string;
  current_stage: Stage;
  target_stage: Stage;
  /** 人类确认的 Prompt 输入；为空将返回 400（E101） */
  human_prompt_input: string;
  pull_back_reason?: string;
}

// ---------- API 响应 ----------

export interface GateDecisionRequest {
  gate_id: string;
  decision: Exclude<GateStatus, "PENDING" | "DECIDED">;
  reason?: string; // REJECTED 时必填
}

export interface FreezeBaselineRequest {
  project_id: string;
  scope: string;
  source_entry_ids: string[];
}

export interface FreezeBaselineResponse {
  baseline_id: string;
  version: string;
  frozen_at: string;
  project_status: "FROZEN";
  blackboard: "READ_ONLY";
}

export interface ChangeRequestBody {
  baseline_id: string;
  description: string;
  impact_scope: string;
  impact_cost: string;
  impact_schedule: string;
}

export interface ChangeDecisionRequest {
  cr_id: string;
  approved: boolean;
  decided_by: string;
}

export interface ApiError {
  code: string; // 如 E002（空引用）、E101（空人类输入）、B301（黑板只读）
  message: string;
  action?: string; // 如 PROJECT_PAUSED、ESCALATE_TO_PM
}

/** 黑板条目（可视化映射见规格书 4.1） */
export interface BlackboardEntry {
  id: string;
  project_id: string;
  stage: Stage;
  source_agent: AgentRole;
  content: string;
  status: EntryStatus;
  is_conflict: boolean;
}
