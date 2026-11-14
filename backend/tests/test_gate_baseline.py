"""T3 / T10 验收自测（供 T11 联调基线）。

运行：pytest backend/tests -v
覆盖规格书 2.2 验收标准：
- T3: AgentMessageRequest 拦截空引用；StageAdvanceRequest 拦截空人类输入
- T10: 校验 signoffs 全部 APPROVED 后才能冻结；冻结后黑板只读
"""
import uuid

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.app import app
from backend.core.enums import (
    AgentRole,
    EntryStatus,
    GateStatus,
    Stage,
)
from backend.core.models import (
    AgentMessage,
    BlackboardEntry,
    HumanGate,
    Signoff,
)
from backend.gate.service import GateService
from backend.store import store
from backend.baseline.service import BaselineService

client = TestClient(app)
gate = GateService()
bs = BaselineService(store)


def _make_entry(project_id: str, status: EntryStatus = EntryStatus.APPROVED) -> BlackboardEntry:
    return BlackboardEntry(
        id=f"e-{uuid.uuid4().hex[:8]}",
        project_id=project_id,
        stage=Stage.IDEA,
        source_agent=AgentRole.PM,
        content="初始上下文卡片",
        status=status,
    )


# ---------- T3: AgentMessageRequest ----------

def test_agent_message_rejects_empty_references():
    """验收点：拦截空引用（references 为空 → 拒收并警告）"""
    project = store.create_project("t-empty-ref")
    msg = AgentMessage(
        id="m1", project_id=project.id, stage=Stage.IDEA,
        agent_role=AgentRole.BA, content="分析", references=[],
    )
    with pytest.raises(HTTPException) as exc:
        gate.validate_agent_message(msg, {}, project)
    assert exc.value.status_code == 400
    assert exc.value.detail["code"] == "E002"


def test_agent_message_rejects_missing_reference_target():
    project = store.create_project("t-bad-ref")
    msg = AgentMessage(
        id="m2", project_id=project.id, stage=Stage.IDEA,
        agent_role=AgentRole.BA, content="分析", references=["not-exist"],
    )
    with pytest.raises(HTTPException) as exc:
        gate.validate_agent_message(msg, {}, project)
    assert exc.value.detail["code"] == "E003"


def test_agent_message_blocks_unapproved_reference():
    """幻觉传染防御：引用未 APPROVED 的条目 → 阻断"""
    project = store.create_project("t-unapproved")
    draft = _make_entry(project.id, EntryStatus.DRAFT)
    store.add_entry(draft)
    msg = AgentMessage(
        id="m3", project_id=project.id, stage=Stage.IDEA,
        agent_role=AgentRole.BA, content="顺着草稿继续说", references=[draft.id],
    )
    with pytest.raises(HTTPException) as exc:
        gate.validate_agent_message(msg, {draft.id: draft}, project)
    assert exc.value.detail["action"] == "PROJECT_PAUSED"


def test_agent_message_accepts_valid():
    project = store.create_project("t-valid")
    ok = _make_entry(project.id)
    store.add_entry(ok)
    msg = AgentMessage(
        id="m4", project_id=project.id, stage=Stage.IDEA,
        agent_role=AgentRole.BA, content="基于卡片分析", references=[ok.id],
    )
    assert gate.validate_agent_message(msg, {ok.id: ok}, project) is msg


# ---------- T3: StageAdvanceRequest ----------

def test_stage_advance_rejects_empty_human_input():
    """验收点：拦截空人类输入（human_prompt_input 为空 → 400）"""
    project = store.create_project("t-advance")
    with pytest.raises(HTTPException) as exc:
        gate.validate_stage_advance(project, Stage.DISCUSSION, "   ")
    assert exc.value.status_code == 400
    assert exc.value.detail["code"] == "E101"


def test_stage_advance_rejects_skip_stage():
    project = store.create_project("t-skip")
    with pytest.raises(HTTPException) as exc:
        gate.validate_stage_advance(project, Stage.PROPOSAL, "确认")
    assert exc.value.detail["code"] == "E102"


def test_stage_advance_accepts_valid():
    project = store.create_project("t-advance-ok")
    gate.validate_stage_advance(project, Stage.DISCUSSION, "人类确认：聚焦核心逻辑")


# ---------- T3: 门禁裁决 ----------

def test_gate_decision_reject_requires_reason():
    project = store.create_project("t-gate")
    entry = _make_entry(project.id, EntryStatus.PENDING_REVIEW)
    store.add_entry(entry)
    g = store.add_gate(HumanGate(id="g1", project_id=project.id, stage=Stage.IDEA, entry_id=entry.id))
    with pytest.raises(HTTPException) as exc:
        gate.decide_gate(g, GateStatus.REJECTED, "")
    assert exc.value.detail["code"] == "E202"

    decided = gate.decide_gate(g, GateStatus.REJECTED, "理由不充分")
    assert decided.gate_status == GateStatus.REJECTED


# ---------- T10: 基线冻结 ----------

def _sign_project(project_id: str, approved: bool):
    parties = ["business", "development", "testing"]
    for party in parties:
        store.add_signoff(Signoff(
            id=f"s-{party}-{uuid.uuid4().hex[:6]}",
            project_id=project_id,
            party=party,
            status=EntryStatus.APPROVED if approved else EntryStatus.DRAFT,
        ))


def test_freeze_requires_all_signoffs_approved():
    project = store.create_project("t-freeze")
    _sign_project(project.id, approved=False)
    with pytest.raises(HTTPException) as exc:
        bs.freeze_baseline(project.id, "全部 APPROVED 条目", [])
    assert exc.value.detail["code"] == "B103"


def test_freeze_success_and_blackboard_readonly():
    project = store.create_project("t-freeze-ok")
    _sign_project(project.id, approved=True)
    bl = bs.freeze_baseline(project.id, "范围：核心链路", [])
    assert bl.version == "V1.0"
    assert project.status.value == "FROZEN"
    with pytest.raises(HTTPException) as exc:
        bs.assert_blackboard_writable(project.id)
    assert exc.value.detail["code"] == "B301"


def test_change_request_updates_version():
    project = store.create_project("t-cr")
    _sign_project(project.id, approved=True)
    bl = bs.freeze_baseline(project.id, "初始基线", [])
    cr = bs.submit_change_request(bl.id, "新增导出功能", "范围+1模块", "+2人天", "+3天")
    assert cr.status == EntryStatus.PENDING_REVIEW
    decided = bs.decide_change_request(cr.id, approved=True, decided_by="pm")
    assert decided.status == EntryStatus.APPROVED
    assert store.get_baseline(bl.id).version == "V1.1"


# ---------- 补充：拍板 DECIDED ----------

def test_gate_decision_decided_requires_reason():
    """拍板 DECIDED：理由必填并记录"""
    project = store.create_project("t-decided")
    entry = _make_entry(project.id, EntryStatus.PENDING_REVIEW)
    store.add_entry(entry)
    g = store.add_gate(HumanGate(id="g2", project_id=project.id, stage=Stage.IDEA, entry_id=entry.id))
    with pytest.raises(HTTPException) as exc:
        gate.decide_gate(g, GateStatus.DECIDED, "")
    assert exc.value.detail["code"] == "E204"

    decided = gate.decide_gate(g, GateStatus.DECIDED, "基于预算现状拍板：通过")
    assert decided.gate_status == GateStatus.DECIDED
    assert decided.reason == "基于预算现状拍板：通过"


# ---------- 补充：会签签署 ----------

def test_signoff_init_and_sign():
    project = store.create_project("t-sign")
    created = bs.init_signoffs(project.id)
    assert sorted(created) == ["business", "development", "testing"]
    so = bs.sign_signoff(project.id, "business", "李业务")
    assert so.status == EntryStatus.APPROVED and so.signed_by == "李业务"


def test_signoff_no_proxy_signing():
    """不可一人代签：同一签署人只能签一个方位"""
    project = store.create_project("t-proxy")
    bs.init_signoffs(project.id)
    bs.sign_signoff(project.id, "business", "王经理")
    with pytest.raises(HTTPException) as exc:
        bs.sign_signoff(project.id, "development", "王经理")
    assert exc.value.detail["code"] == "B405"


def test_signoff_rejects_duplicate_sign():
    project = store.create_project("t-dup")
    bs.init_signoffs(project.id)
    bs.sign_signoff(project.id, "testing", "赵测试")
    with pytest.raises(HTTPException) as exc:
        bs.sign_signoff(project.id, "testing", "赵测试")
    assert exc.value.detail["code"] == "B404A"


# ---------- HTTP 层冒烟 ----------

def test_http_gate_advance_validate_returns_400_on_empty_input():
    project = store.create_project("t-http")
    resp = client.post("/gate/advance/validate", json={
        "project_id": project.id,
        "current_stage": "IDEA",
        "target_stage": "DISCUSSION",
        "human_prompt_input": "",
    })
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "E101"


def test_http_health():
    assert client.get("/health").json()["status"] == "ok"
