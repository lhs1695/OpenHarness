# ForgeFlow HTTP API

> Base URL：`http://<host>:8000`（默认，见 `docker-compose.yml`）。
> 版本前缀：`/api/v1`。V1 为单用户/单租户，**无鉴权**（认证留待后续版本）。

## 概览

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/v1/tasks` | 创建任务 |
| GET | `/api/v1/tasks` | 列出任务 |
| GET | `/api/v1/tasks/{task_id}` | 查询任务 |
| POST | `/api/v1/tasks/{task_id}/start` | 启动任务（`?command_id=` 幂等键） |
| POST | `/api/v1/tasks/{task_id}/pause` | 暂停任务 |
| POST | `/api/v1/tasks/{task_id}/resume` | 恢复任务 |
| POST | `/api/v1/tasks/{task_id}/cancel` | 取消任务 |
| GET | `/api/v1/tasks/{task_id}/approvals` | 列出任务审批 |
| POST | `/api/v1/approvals/{approval_id}/approve` | 通过审批 |
| POST | `/api/v1/approvals/{approval_id}/reject` | 拒绝审批 |
| GET | `/api/v1/tasks/{task_id}/timeline` | 时间线（结构化事件） |
| GET | `/api/v1/tasks/{task_id}/trace` | Trace JSONL 导出 |
| GET | `/api/v1/tasks/{task_id}/events` | SSE 实时事件流 |

## 任务接口

### POST `/api/v1/tasks` — 创建任务

请求体（`CreateTaskRequest`）：

```json
{
  "repository": "billing-service",
  "title": "修复重复扣款",
  "description": "客户端超时重试时可能产生第二笔扣款",
  "task_type": "bugfix",
  "priority": "P2",
  "acceptance_criteria": ["相同幂等键只产生一笔支付记录"],
  "risk_tags": ["payment", "idempotency"],
  "requested_by": "backend-team",
  "initial_risk_score": null
}
```

响应 `200`（`TaskView`）：

```json
{
  "id": "task_1a2b3c4d",
  "repository": "billing-service",
  "title": "修复重复扣款",
  "description": "客户端超时重试时可能产生第二笔扣款",
  "task_type": "bugfix",
  "priority": "P2",
  "status": "DRAFT",
  "initial_risk_score": 0,
  "final_risk_score": null,
  "requested_by": "backend-team",
  "created_at": "2026-08-05T05:07:01.319525+00:00",
  "updated_at": "2026-08-05T05:07:01.319525+00:00"
}
```

### GET `/api/v1/tasks` — 列出任务

响应 `200`：`TaskView` 数组（按创建时间升序）。

### GET `/api/v1/tasks/{task_id}` — 查询任务

响应 `200`：`TaskView`；不存在返回 `404`。

### POST `/api/v1/tasks/{task_id}/start` — 启动任务

查询参数 `command_id`（可选）：**幂等键**。重复投递同一 `command_id` 为 no-op，不会重复执行关键业务（Celery 重投递防重）。

响应 `200`：`TaskView`（异步编排，最终状态见后续 GET）。

### POST `/api/v1/tasks/{task_id}/pause | resume | cancel`

- `pause`：从可执行态进入 `PAUSED`（Checkpoint 恢复留待后续）；
- `resume`：`PAUSED` → `READY`（恢复目标为 `resume_target`）；
- `cancel`：可执行态进入 `CANCEL_REQUESTED` → 后台终止子进程 → `CANCELLED`；DRAFT 等非可执行态为 no-op。

响应 `200`：`TaskView`。

## 审批接口

### GET `/api/v1/tasks/{task_id}/approvals`

响应 `200`：

```json
[
  {
    "id": "approval-1",
    "task_id": "task_1a2b3c4d",
    "approval_type": "plan",
    "status": "pending",
    "requested_reason": "plan approval for task task_1a2b3c4d"
  }
]
```

### POST `/api/v1/approvals/{approval_id}/approve` / `/reject`

请求体（`ApprovalResolveRequest`）：

```json
{ "approved": true, "resolved_by": "backend_owner", "reason": "计划合理" }
```

响应 `200`：`{approval_id, approved, resolved_by, resolved_at}`。

**幂等**：同一审批重复解决返回首次结果，不重复审计。

## Trace 接口

### GET `/api/v1/tasks/{task_id}/timeline`

响应 `200`：按时间排序的事件数组：

```json
[
  {
    "timestamp": "2026-08-05T05:07:01.319525+00:00",
    "event_type": "task_state_changed",
    "span_id": "…",
    "parent_event_id": null,
    "status": "ok",
    "summary": null,
    "latency_ms": null
  }
]
```

### GET `/api/v1/tasks/{task_id}/trace`

响应 `200`：`text/plain`，Trace JSONL（每行一个 `SpanEvent`）。

### GET `/api/v1/tasks/{task_id}/events` — SSE

响应 `200`，`Content-Type: text/event-stream`。格式：

```text
event: task_state_changed
data: {"task_id":"…","type":"task_state_changed","occurred_at":"…","payload":{...}}

event: heartbeat
data: {}
```

事件类型：`task_created`、`task_state_changed`、`approval_resolved` 等。

## 错误码

| 状态码 | 场景 |
|---|---|
| `404` | 任务/审批不存在 |
| `422` | 请求体校验失败 |
| `500` | 服务端异常（结构化日志含 task_id/run_id） |
