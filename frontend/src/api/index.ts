/**
 * /frontend/src/api —— 冻结版 API Client 出口（V1.0）。
 * 下游（dashboard、gate 面板、会签页等视图）只允许从此处导入，
 * 不得自行拼接请求。契约变更须走 /docs/adr 流程。
 */
export { ApiClient, ApiRequestError, apiClient } from "./client";
export type { ApiClientOptions } from "./client";
export type {
  AgentMessageRequest,
  AgentRole,
  BlackboardEntry,
  ChangeDecisionRequest,
  ChangeRequestBody,
  EntryStatus,
  FreezeBaselineRequest,
  FreezeBaselineResponse,
  GateDecisionRequest,
  GateStatus,
  ProjectStatus,
  RoundStatus,
  SignoffSignRequest,
  Stage,
  StageAdvanceRequest,
  StageStatus,
} from "./types";
export { MAX_ROUNDS } from "./types";
