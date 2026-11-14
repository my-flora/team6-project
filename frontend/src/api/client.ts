/**
 * 前端 API Client —— V1.0 冻结（Owner：陈欣然）。
 *
 * 端点与 /contracts 契约一一对应：
 * - POST /gate/messages/validate   AgentMessageRequest 校验（空引用 → 400 E002）
 * - POST /gate/advance/validate    StageAdvanceRequest 校验（空人类输入 → 400 E101）
 * - POST /gate/decision            人类门禁裁决（驳回必填 reason）
 * - POST /baseline/freeze          冻结基线（三方会签须全绿）
 * - POST /baseline/change-requests 提交变更申请
 * - POST /baseline/change-requests/decision 审批变更
 */
import type {
  AgentMessageRequest,
  ApiError,
  ChangeDecisionRequest,
  ChangeRequestBody,
  FreezeBaselineRequest,
  FreezeBaselineResponse,
  GateDecisionRequest,
  SignoffSignRequest,
  StageAdvanceRequest,
} from "./types";

export interface ApiClientOptions {
  baseUrl?: string;
  fetchImpl?: typeof fetch;
}

export class ApiRequestError extends Error {
  constructor(public readonly error: ApiError, public readonly status: number) {
    super(`[${error.code}] ${error.message}`);
    this.name = "ApiRequestError";
  }
}

export class ApiClient {
  private readonly baseUrl: string;
  private readonly fetchImpl: typeof fetch;

  constructor(options: ApiClientOptions = {}) {
    this.baseUrl = (options.baseUrl ?? "/api").replace(/\/$/, "");
    this.fetchImpl = options.fetchImpl ?? fetch.bind(globalThis);
  }

  private async request<T>(path: string, body: unknown): Promise<T> {
    const resp = await this.fetchImpl(`${this.baseUrl}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!resp.ok) {
      const payload = (await resp.json().catch(() => null)) as { detail?: ApiError } | null;
      const detail: ApiError = payload?.detail ?? { code: "E999", message: `HTTP ${resp.status}` };
      throw new ApiRequestError(detail, resp.status);
    }
    return (await resp.json()) as T;
  }

  // ---------- T3 门禁与契约校验 ----------

  /** 校验 Agent 发言；空引用将抛 ApiRequestError(code=E002) */
  validateAgentMessage(req: AgentMessageRequest): Promise<{ valid: true }> {
    return this.request("/gate/messages/validate", req);
  }

  /** 校验阶段推进；空人类输入将抛 ApiRequestError(code=E101)，前端据此灰显推进按钮 */
  validateStageAdvance(req: StageAdvanceRequest): Promise<{ valid: true }> {
    return this.request("/gate/advance/validate", req);
  }

  /** 门禁裁决：APPROVED / REJECTED（必填 reason）/ DECIDED（拍板，必填 reason） */
  decideGate(req: GateDecisionRequest): Promise<{ gate_id: string; gate_status: string; entry_status: string | null }> {
    if ((req.decision === "REJECTED" || req.decision === "DECIDED") && !(req.reason ?? "").trim()) {
      return Promise.reject(new ApiRequestError(
        { code: req.decision === "REJECTED" ? "E202" : "E204", message: req.decision === "REJECTED" ? "驳回必须填写 reason" : "人类拍板必须记录裁决理由" },
        400,
      ));
    }
    return this.request("/gate/decision", req);
  }

  /** 初始化三方会签单 */
  initSignoffs(project_id: string): Promise<{ created: string[]; parties: string[] }> {
    return this.request("/baseline/signoffs/init", { project_id, scope: "", source_entry_ids: [] });
  }

  /** 签署会签单；一人已签另一方将返回 B405（不可一人代签） */
  signSignoff(req: SignoffSignRequest): Promise<{ party: string; status: string; signed_by: string }> {
    return this.request("/baseline/signoffs", req);
  }

  // ---------- T10 基线冻结与变更 ----------

  freezeBaseline(req: FreezeBaselineRequest): Promise<FreezeBaselineResponse> {
    return this.request("/baseline/freeze", req);
  }

  submitChangeRequest(req: ChangeRequestBody): Promise<{ cr_id: string; status: string }> {
    return this.request("/baseline/change-requests", req);
  }

  decideChangeRequest(req: ChangeDecisionRequest): Promise<{ cr_id: string; status: string; decided_by: string }> {
    return this.request("/baseline/change-requests/decision", req);
  }

  // ---------- 健康检查 ----------

  async health(): Promise<{ status: string; contracts_version: string }> {
    const resp = await this.fetchImpl(`${this.baseUrl}/health`);
    if (!resp.ok) throw new ApiRequestError({ code: "E999", message: `HTTP ${resp.status}` }, resp.status);
    return resp.json();
  }
}

export const apiClient = new ApiClient();
