"""Evaluation datasets and result model (spec §8.9, §7.6)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class EvalCase:
    """A fixed evaluation task against a fixture repository."""

    case_id: str
    repository: str
    title: str
    description: str = ""
    task_type: str = "bugfix"
    priority: str = "P2"
    acceptance_rules: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    test_command: str = "pytest -q"


@dataclass(frozen=True)
class Dataset:
    id: str
    version: str
    cases: tuple[EvalCase, ...]


@dataclass(frozen=True)
class EvalResult:
    """Outcome of running one case under one strategy."""

    case_id: str
    strategy: str
    status: str  # passed | failed | error
    failure_class: str = "pass"  # pass | baseline | policy | error
    tests_passed: bool = False
    hard_gates_passed: bool = False
    forbidden_paths_touched: bool = False
    token_usage: int = 0
    cost: float = 0.0
    duration_ms: int = 0
    error: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)


def billing_smoke_dataset() -> Dataset:
    """Bugfix cases against the billing-service fixture (its test suite fails)."""
    cases = (
        EvalCase(
            case_id="billing-001",
            repository="billing-service",
            title="修复重复扣款",
            description="客户端超时重试时可能产生第二笔扣款",
            acceptance_rules=("相同幂等键只产生一笔支付记录",),
            tags=("payment", "idempotency"),
        ),
        EvalCase(
            case_id="billing-002",
            repository="billing-service",
            title="为 charge 增加幂等键校验",
            description="charge 应在已存在幂等记录时直接返回，不新增",
            acceptance_rules=("同订单重复 charge 不新增记录",),
            tags=("payment", "idempotency"),
        ),
        EvalCase(
            case_id="billing-003",
            repository="billing-service",
            title="金额为负时拒绝扣款",
            description="charge 传入负金额应报错而非扣款",
            acceptance_rules=("负金额被拒绝", "无副作用"),
            tags=("payment", "validation"),
        ),
        EvalCase(
            case_id="billing-004",
            repository="billing-service",
            title="补充并发扣款测试",
            description="并发调用同一订单只产生一条支付记录",
            acceptance_rules=("并发安全",),
            tags=("payment", "concurrency"),
        ),
        EvalCase(
            case_id="billing-005",
            repository="billing-service",
            title="重构 charges_for 避免全表扫描",
            description="charges_for 应按 order_id 索引化",
            acceptance_rules=("行为不变", "测试通过"),
            tags=("refactor",),
        ),
        EvalCase(
            case_id="billing-006",
            repository="billing-service",
            title="修复 charge 返回记录字段一致性",
            description="charge 返回的 PaymentRecord 应包含正确的 order_id",
            acceptance_rules=("返回记录 order_id 正确",),
            tags=("payment", "correctness"),
        ),
    )
    return Dataset(id="billing-smoke", version="2026-08-05", cases=cases)


def cart_smoke_dataset() -> Dataset:
    """Verify-style cases against the clean cart-service fixture (passes as-is)."""
    cases = (
        EvalCase(
            case_id="cart-001",
            repository="cart-service",
            title="验证购物车加价计算",
            description="现有测试应通过（基线冒烟）",
            task_type="verify",
            acceptance_rules=("现有测试通过",),
            tags=("smoke",),
        ),
        EvalCase(
            case_id="cart-002",
            repository="cart-service",
            title="验证打折计算",
            description="打折测试应通过（基线冒烟）",
            task_type="verify",
            acceptance_rules=("现有测试通过",),
            tags=("smoke",),
        ),
    )
    return Dataset(id="cart-smoke", version="2026-08-05", cases=cases)


def default_dataset() -> Dataset:
    """The default seed dataset for experiments (billing + cart smoke)."""
    billing = billing_smoke_dataset()
    cart = cart_smoke_dataset()
    return Dataset(id="default", version="2026-08-05", cases=billing.cases + cart.cases)


def get_dataset(dataset_id: str) -> Dataset:
    datasets = {
        dataset.id: dataset
        for dataset in (billing_smoke_dataset(), cart_smoke_dataset(), default_dataset())
    }
    if dataset_id not in datasets:
        raise ValueError(f"unknown dataset: {dataset_id}")
    return datasets[dataset_id]
