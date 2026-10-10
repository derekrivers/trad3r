"""Pure P4.5 exposure, protection and management-permission evaluation.

This module has no persistence, adapter or dispatch capability. Its output is a
diagnostic derived from already validated synthetic account evidence, never an
authorization token.
"""
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal as D

from .ledger import utc
from .risk import money
from . import order_store as store


MODE = "synthetic_protection_evaluation_only"
SCHEMA = "order-protection-evaluation-v1"
MAX_EVIDENCE_AGE = timedelta(seconds=60)
DESIRED_ACTIONS = {"hold", "cancel_entry_remainder", "flatten"}

ENTRY = "entry"
STOP = "protective_stop"
EXIT = "reducing_exit"
PURPOSES = {ENTRY, STOP, EXIT}

POSSIBLY_LIVE = {
    "reserved", "submitting", "acknowledged", "working", "partially_filled",
    "unknown", "cancel_pending",
}
ACTIVE = {"acknowledged", "working", "partially_filled"}
PENDING = {"reserved", "submitting"}
UNCERTAIN = {"unknown", "cancel_pending"}
TERMINAL = {"filled", "cancelled", "rejected"}
STATES = POSSIBLY_LIVE | TERMINAL


def _bool(value, label):
    if type(value) is not bool:
        raise ValueError(f"{label} must be boolean")
    return value


def _quantity(value, label, *, allow_zero=True):
    if type(value) is not int or value < 0 or (not allow_zero and value == 0):
        raise ValueError(f"{label} must be a {'nonnegative' if allow_zero else 'positive'} whole quantity")
    return value


def _nonnegative(value, label):
    value = money(value)
    if value < 0:
        raise ValueError(f"{label} must be nonnegative")
    return value


@dataclass(frozen=True)
class Incident:
    incident_id: str
    blocks_management: bool = False
    blocks_cancellation: bool = False

    def __post_init__(self):
        store._identity(self.incident_id, "protection incident id")
        _bool(self.blocks_management, "blocks management")
        _bool(self.blocks_cancellation, "blocks cancellation")


@dataclass(frozen=True)
class OrderProjection:
    order_id: str
    instrument_id: str
    purpose: str
    state: str
    original_quantity: int
    executed_quantity: int
    last_event_version: int
    mapping_verified: bool = True
    evidence_complete: bool = True
    terminal_no_remainder_proved: bool = False
    confirmed_stop_price_usd: D | str | None = None
    fee_allocation_usd: D | str = D("0")

    def __post_init__(self):
        store._identity(self.order_id, "protection order id")
        store._identity(self.instrument_id, "protection instrument id")
        if self.purpose not in PURPOSES or self.state not in STATES:
            raise ValueError("Invalid protection order purpose or state")
        _quantity(self.original_quantity, "original order quantity", allow_zero=False)
        _quantity(self.executed_quantity, "executed order quantity")
        if self.executed_quantity > self.original_quantity:
            raise ValueError("Executed order quantity exceeds original quantity")
        store._version(self.last_event_version, "protection order event version")
        for field in ("mapping_verified", "evidence_complete", "terminal_no_remainder_proved"):
            _bool(getattr(self, field), field.replace("_", " "))
        if self.state == "filled" and self.executed_quantity != self.original_quantity:
            raise ValueError("Filled order does not account for its full quantity")
        if self.state == "rejected" and self.executed_quantity:
            raise ValueError("Rejected order has executions")
        if self.terminal_no_remainder_proved and self.state not in ("cancelled", "rejected"):
            raise ValueError("Terminal remainder proof requires a cancelled or rejected order")
        price = self.confirmed_stop_price_usd
        if price is not None:
            price = money(price)
            if price <= 0 or self.purpose != STOP:
                raise ValueError("Only protective stops can carry a positive confirmed stop price")
            object.__setattr__(self, "confirmed_stop_price_usd", price)
        fee = _nonnegative(self.fee_allocation_usd, "exit fee allocation")
        if self.purpose == ENTRY and fee:
            raise ValueError("Entry order cannot consume the reducing-exit fee allocation")
        object.__setattr__(self, "fee_allocation_usd", fee)

    @property
    def remainder(self):
        if self.state == "filled":
            return 0
        if self.state in ("cancelled", "rejected") and self.terminal_no_remainder_proved:
            return 0
        return self.original_quantity - self.executed_quantity


@dataclass(frozen=True)
class ProtectionSnapshot:
    account_id: str
    environment: str
    instrument_id: str
    account_version: int
    evidence_version: int
    execution_watermark: int
    snapshot_id: str
    snapshot_at: str
    quantity: int
    orders: tuple[OrderProjection, ...] = ()
    incidents: tuple[Incident, ...] = ()
    halt_reasons: tuple[str, ...] = ()
    operator_paused: bool = False
    desired_action: str = "hold"
    quantity_verified: bool = True
    evidence_complete: bool = True
    order_inventory_complete: bool = True
    identity_consistent: bool = True
    store_valid: bool = True
    fee_evidence_bounded: bool = True
    fee_evidence_complete: bool = True
    writer_fenced: bool = True
    session_supported: bool = True
    planned_stop_price_usd: D | str | None = None
    quote_at: str | None = None
    fx_at: str | None = None
    exit_fee_allowance_usd: D | str = D("0")
    exit_fees_incurred_usd: D | str = D("0")
    settled_cash_usd: D | str = D("0")

    def __post_init__(self):
        store._identity(self.account_id, "protection account id")
        if self.environment != "synthetic":
            raise ValueError("Protection evaluation supports synthetic accounts only")
        store._identity(self.instrument_id, "protection instrument id")
        store._version(self.account_version, "protection account version")
        store._version(self.evidence_version, "protection evidence version")
        store._version(self.execution_watermark, "protection execution watermark")
        store._identity(self.snapshot_id, "protection snapshot id")
        store._timestamp_string(self.snapshot_at, "protection snapshot time")
        _quantity(self.quantity, "verified position quantity")
        if not isinstance(self.orders, tuple) or any(not isinstance(row, OrderProjection) for row in self.orders):
            raise ValueError("Protection orders must be an immutable tuple")
        if len({row.order_id for row in self.orders}) != len(self.orders):
            raise ValueError("Protection order identities must be unique")
        if not isinstance(self.incidents, tuple) or any(not isinstance(row, Incident) for row in self.incidents):
            raise ValueError("Protection incidents must be an immutable tuple")
        if len({row.incident_id for row in self.incidents}) != len(self.incidents):
            raise ValueError("Protection incident identities must be unique")
        if (not isinstance(self.halt_reasons, tuple)
                or self.halt_reasons != tuple(sorted(set(self.halt_reasons)))
                or any(not isinstance(reason, str) or not reason for reason in self.halt_reasons)):
            raise ValueError("Halt reasons must be a sorted unique tuple")
        if self.desired_action not in DESIRED_ACTIONS:
            raise ValueError("Invalid desired protection action")
        for field in (
                "operator_paused", "quantity_verified", "evidence_complete",
                "order_inventory_complete", "identity_consistent", "store_valid",
                "fee_evidence_bounded", "fee_evidence_complete", "writer_fenced",
                "session_supported"):
            _bool(getattr(self, field), field.replace("_", " "))
        stop = self.planned_stop_price_usd
        if stop is not None:
            stop = money(stop)
            if stop <= 0:
                raise ValueError("Planned stop price must be positive")
            object.__setattr__(self, "planned_stop_price_usd", stop)
        for field in ("quote_at", "fx_at"):
            value = getattr(self, field)
            if value is not None:
                store._timestamp_string(value, field.replace("_", " "))
        for field in ("exit_fee_allowance_usd", "exit_fees_incurred_usd", "settled_cash_usd"):
            object.__setattr__(self, field, _nonnegative(getattr(self, field), field.replace("_", " ")))


@dataclass(frozen=True)
class EvaluationRequest:
    at: str
    expected_account_version: int
    expected_evidence_version: int
    reduction_quantity: int | None = None
    reduction_fee_bound_usd: D | str = D("0")
    cancel_order_id: str | None = None

    def __post_init__(self):
        store._timestamp_string(self.at, "protection evaluation time")
        store._version(self.expected_account_version, "expected protection account version")
        store._version(self.expected_evidence_version, "expected protection evidence version")
        if self.reduction_quantity is not None:
            _quantity(self.reduction_quantity, "requested reduction quantity", allow_zero=False)
        fee = _nonnegative(self.reduction_fee_bound_usd, "requested reduction fee bound")
        if self.reduction_quantity is None and fee:
            raise ValueError("A fee bound requires a requested reduction")
        object.__setattr__(self, "reduction_fee_bound_usd", fee)
        if self.cancel_order_id is not None:
            store._identity(self.cancel_order_id, "cancel target order id")


@dataclass(frozen=True)
class Evaluation:
    schema: str
    mode: str
    account_id: str
    environment: str
    instrument_id: str
    account_version: int
    evidence_version: int
    execution_watermark: int
    snapshot_id: str
    as_of: str
    desired_action: str
    exposure_state: str
    protection_state: str
    verified_quantity: int | None
    covered_quantity: int
    committed_sell_quantity: int
    available_sell_quantity: int | None
    available_exit_fee_usd: str | None
    entry_allowed: bool
    entry_blocked_reasons: tuple[str, ...]
    cancellation_allowed: bool
    cancellation_blocked_reasons: tuple[str, ...]
    reduction_allowed: bool
    reduction_blocked_reasons: tuple[str, ...]
    live_trading_enabled: bool


def _evidence_reason(label, raw, at):
    if raw is None:
        return label + "_missing"
    observed = utc(raw)
    if observed > at:
        return label + "_future"
    if at - observed > MAX_EVIDENCE_AGE:
        return label + "_stale"
    return None


def evaluate(snapshot: ProtectionSnapshot, request: EvaluationRequest) -> Evaluation:
    """Evaluate diagnostic protection facts and request-specific permissions."""
    if not isinstance(snapshot, ProtectionSnapshot) or not isinstance(request, EvaluationRequest):
        raise ValueError("Protection evaluation requires typed snapshot and request inputs")
    at = utc(request.at)
    sell_orders = tuple(row for row in snapshot.orders if row.purpose in (STOP, EXIT))
    entry_orders = tuple(row for row in snapshot.orders if row.purpose == ENTRY)
    committed_sell = sum(row.remainder for row in sell_orders)
    possible_entry = sum(row.remainder for row in entry_orders)
    instrument_mismatch = any(row.instrument_id != snapshot.instrument_id for row in snapshot.orders)

    fact_reasons = []
    if not snapshot.store_valid:
        fact_reasons.append("store_invalid")
    if not snapshot.evidence_complete:
        fact_reasons.append("snapshot_incomplete")
    if not snapshot.order_inventory_complete:
        fact_reasons.append("order_inventory_incomplete")
    if not snapshot.quantity_verified:
        fact_reasons.append("quantity_unverified")
    if not snapshot.identity_consistent or instrument_mismatch:
        fact_reasons.append("identity_conflict")
    available_sell = snapshot.quantity - committed_sell
    if available_sell < 0:
        fact_reasons.append("sell_capacity_conflict")
        available_sell_result = None
    else:
        available_sell_result = available_sell
    if snapshot.quantity == 0 and (possible_entry or committed_sell):
        fact_reasons.append("possible_order_prevents_flatness")

    exposure = ("unresolved" if fact_reasons else
                "verified_long" if snapshot.quantity else "verified_flat")
    if exposure == "unresolved":
        available_sell_result = None

    active_coverage = 0
    pending_stop = False
    uncertain_stop = False
    rejected_stops = []
    protection_reasons = []
    for order in sell_orders:
        if order.purpose != STOP:
            continue
        if order.state in UNCERTAIN or (order.state in ("cancelled", "rejected")
                                        and not order.terminal_no_remainder_proved):
            uncertain_stop = True
        elif order.state in PENDING and order.remainder:
            pending_stop = True
        elif order.state in ACTIVE and order.remainder:
            if not order.mapping_verified:
                protection_reasons.append("protection_identity_unverified")
            elif not order.evidence_complete:
                protection_reasons.append("protection_evidence_incomplete")
            elif order.confirmed_stop_price_usd is None:
                protection_reasons.append("protection_price_unconfirmed")
            elif snapshot.planned_stop_price_usd is None:
                protection_reasons.append("planned_stop_missing")
            elif order.confirmed_stop_price_usd < snapshot.planned_stop_price_usd:
                protection_reasons.append("protection_price_unacceptable")
            else:
                active_coverage += order.remainder
        elif order.state == "rejected" and order.terminal_no_remainder_proved:
            rejected_stops.append(order)
    if active_coverage > snapshot.quantity:
        exposure = "unresolved"
        available_sell_result = None
        if "sell_capacity_conflict" not in fact_reasons:
            fact_reasons.append("sell_capacity_conflict")

    if exposure == "unresolved":
        protection = "unknown"
    elif exposure == "verified_flat":
        protection = "not_required"
    elif uncertain_stop:
        protection = "unknown"
    elif active_coverage == snapshot.quantity:
        protection = "active"
    elif active_coverage:
        protection = "partial"
    elif pending_stop:
        protection = "pending"
    elif rejected_stops:
        stop_orders = tuple(row for row in snapshot.orders if row.purpose == STOP)
        latest_version = max(row.last_event_version for row in stop_orders)
        latest = tuple(row for row in stop_orders if row.last_event_version == latest_version)
        protection = ("rejected" if len(latest) == 1 and latest[0].state == "rejected"
                      and latest[0].terminal_no_remainder_proved else "missing")
    else:
        protection = "missing"

    outstanding_fees = sum(row.fee_allocation_usd for row in sell_orders if row.remainder)
    fee_available = (snapshot.exit_fee_allowance_usd - snapshot.exit_fees_incurred_usd
                     - outstanding_fees)
    fee_conflict = fee_available < 0 or outstanding_fees > snapshot.settled_cash_usd
    available_fee_result = None if fee_conflict else str(fee_available)

    entry_reasons = list(fact_reasons)
    snapshot_time_reason = _evidence_reason("snapshot", snapshot.snapshot_at, at)
    if snapshot_time_reason:
        entry_reasons.append(snapshot_time_reason)
    if snapshot.operator_paused:
        entry_reasons.append("operator_paused")
    if snapshot.desired_action != "hold":
        entry_reasons.append("desired_action:" + snapshot.desired_action)
    entry_reasons.extend("halt:" + reason for reason in snapshot.halt_reasons)
    entry_reasons.extend("incident:" + row.incident_id for row in snapshot.incidents)
    if exposure == "verified_long":
        entry_reasons.append("position_open")
    if exposure == "verified_long" and protection != "active":
        entry_reasons.append("protection:" + protection)
    if not snapshot.fee_evidence_complete:
        entry_reasons.append("fee_evidence_incomplete")
    entry_reasons.extend(protection_reasons)

    version_reasons = []
    if request.expected_account_version != snapshot.account_version:
        version_reasons.append("account_version_changed")
    if request.expected_evidence_version != snapshot.evidence_version:
        version_reasons.append("evidence_version_changed")

    cancel_reasons = list(version_reasons)
    if request.cancel_order_id is None:
        cancel_reasons.append("cancel_not_requested")
    if not snapshot.store_valid:
        cancel_reasons.append("store_invalid")
    if not snapshot.writer_fenced:
        cancel_reasons.append("writer_not_fenced")
    cancel_snapshot_reason = _evidence_reason("snapshot", snapshot.snapshot_at, at)
    if cancel_snapshot_reason == "snapshot_future":
        cancel_reasons.append(cancel_snapshot_reason)
    cancel_reasons.extend("incident:" + row.incident_id for row in snapshot.incidents
                          if row.blocks_cancellation)
    target = next((row for row in snapshot.orders if row.order_id == request.cancel_order_id), None)
    if request.cancel_order_id is not None:
        if target is None:
            cancel_reasons.append("cancel_target_unknown")
        else:
            if target.instrument_id != snapshot.instrument_id or not target.mapping_verified:
                cancel_reasons.append("cancel_identity_unverified")
            if target.remainder == 0:
                cancel_reasons.append("cancel_target_terminal")

    reduction_reasons = list(version_reasons)
    if request.reduction_quantity is None:
        reduction_reasons.append("reduction_not_requested")
    if not snapshot.writer_fenced:
        reduction_reasons.append("writer_not_fenced")
    if not snapshot.session_supported:
        reduction_reasons.append("unsupported_session")
    reduction_reasons.extend(fact_reasons)
    reduction_reasons.extend("incident:" + row.incident_id for row in snapshot.incidents
                             if row.blocks_management)
    for label, raw in (("snapshot", snapshot.snapshot_at),
                       ("quote", snapshot.quote_at), ("fx", snapshot.fx_at)):
        reason = _evidence_reason(label, raw, at)
        if reason:
            reduction_reasons.append(reason)
    if exposure != "verified_long":
        reduction_reasons.append("verified_long_position_required")
    if possible_entry:
        reduction_reasons.append("entry_remainder_possible")
    if not snapshot.fee_evidence_bounded:
        reduction_reasons.append("fee_exposure_unbounded")
    if fee_conflict:
        reduction_reasons.append("fee_allocation_conflict")
    if request.reduction_quantity is not None and available_sell_result is not None:
        if request.reduction_quantity > available_sell_result:
            reduction_reasons.append("sell_quantity_unavailable")
        if (not fee_conflict and request.reduction_fee_bound_usd > fee_available):
            reduction_reasons.append("exit_fee_allowance_unavailable")
        free_fee_cash = snapshot.settled_cash_usd - outstanding_fees
        if request.reduction_fee_bound_usd > free_fee_cash:
            reduction_reasons.append("settled_cash_fee_unavailable")

    return Evaluation(
        schema=SCHEMA, mode=MODE, account_id=snapshot.account_id,
        environment=snapshot.environment, instrument_id=snapshot.instrument_id,
        account_version=snapshot.account_version, evidence_version=snapshot.evidence_version,
        execution_watermark=snapshot.execution_watermark, snapshot_id=snapshot.snapshot_id,
        as_of=at.isoformat(), desired_action=snapshot.desired_action,
        exposure_state=exposure, protection_state=protection,
        verified_quantity=snapshot.quantity if snapshot.quantity_verified else None,
        covered_quantity=active_coverage, committed_sell_quantity=committed_sell,
        available_sell_quantity=available_sell_result,
        available_exit_fee_usd=available_fee_result,
        entry_allowed=not entry_reasons,
        entry_blocked_reasons=tuple(sorted(set(entry_reasons))),
        cancellation_allowed=not cancel_reasons,
        cancellation_blocked_reasons=tuple(sorted(set(cancel_reasons))),
        reduction_allowed=not reduction_reasons,
        reduction_blocked_reasons=tuple(sorted(set(reduction_reasons))),
        live_trading_enabled=False,
    )
