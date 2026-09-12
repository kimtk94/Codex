from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Mapping, Sequence

from .contracts import Mode, stable_hash


def _stable_id(prefix: str, payload: dict) -> str:
    return f"{prefix}-{stable_hash(payload)[:20]}"


@dataclass(frozen=True)
class ExecutionPolicy:
    max_symbol_weight: float = 0.75
    max_gross_weight: float = 1.00
    min_order_notional: float = 10.0
    max_single_order_fraction: float = 0.80
    max_total_turnover_fraction: float = 2.00
    long_only: bool = True
    allow_live_execution: bool = False
    broker: str = "SHADOW"
    slippage_bps: float = 0.0
    commission_bps: float = 0.0

    def __post_init__(self) -> None:
        if not 0 < self.max_symbol_weight <= 1:
            raise ValueError("max_symbol_weight must be in (0, 1]")
        if not 0 < self.max_gross_weight <= 1:
            raise ValueError("max_gross_weight must be in (0, 1]")
        if self.min_order_notional < 0:
            raise ValueError("min_order_notional must be >= 0")
        if self.max_single_order_fraction <= 0:
            raise ValueError("max_single_order_fraction must be > 0")
        if self.max_total_turnover_fraction <= 0:
            raise ValueError("max_total_turnover_fraction must be > 0")
        if self.slippage_bps < 0 or self.commission_bps < 0:
            raise ValueError("cost assumptions must be >= 0")
        if self.broker.upper() != "SHADOW":
            raise ValueError("LEAN execution contract v1 only supports SHADOW broker")


@dataclass(frozen=True)
class PortfolioTargetContract:
    target_id: str
    run_id: str
    strategy_version: str
    symbol: str
    decision_ts: str
    effective_ts: str
    target_weight: float
    source: str

    @classmethod
    def build(
        cls,
        *,
        run_id: str,
        strategy_version: str,
        symbol: str,
        decision_ts: str,
        effective_ts: str,
        target_weight: float,
        source: str,
    ) -> "PortfolioTargetContract":
        payload = {
            "run_id": run_id,
            "strategy_version": strategy_version,
            "symbol": symbol.upper(),
            "decision_ts": decision_ts,
            "effective_ts": effective_ts,
            "target_weight": float(target_weight),
            "source": source,
        }
        return cls(
            target_id=_stable_id("pt", payload),
            run_id=run_id,
            strategy_version=strategy_version,
            symbol=symbol.upper(),
            decision_ts=decision_ts,
            effective_ts=effective_ts,
            target_weight=float(target_weight),
            source=source,
        )


@dataclass(frozen=True)
class RiskAdjustedTarget:
    target_id: str
    run_id: str
    strategy_version: str
    symbol: str
    decision_ts: str
    effective_ts: str
    original_weight: float
    adjusted_weight: float
    risk_reason: str
    source: str


@dataclass(frozen=True)
class OrderIntent:
    intent_id: str
    target_id: str
    run_id: str
    strategy_version: str
    symbol: str
    side: str
    quantity: float
    current_quantity: float
    target_quantity: float
    reference_price: float
    notional: float
    decision_ts: str
    effective_ts: str
    risk_reducing: bool
    mode: str


@dataclass(frozen=True)
class GatedOrderIntent:
    intent: OrderIntent
    status: str
    risk_reason: str


@dataclass(frozen=True)
class BrokerOrder:
    broker_order_id: str
    client_order_id: str
    intent_id: str
    symbol: str
    side: str
    quantity: float
    order_type: str
    time_in_force: str
    broker: str
    status: str
    effective_ts: str
    mode: str


@dataclass(frozen=True)
class ExecutionFill:
    fill_id: str
    broker_order_id: str
    intent_id: str
    symbol: str
    side: str
    quantity: float
    fill_price: float
    fee: float
    fill_ts: str
    broker: str
    status: str


@dataclass(frozen=True)
class ExecutionState:
    cash: float
    positions: dict[str, float]


@dataclass(frozen=True)
class ExecutionCycleResult:
    adjusted_targets: list[RiskAdjustedTarget]
    gated_intents: list[GatedOrderIntent]
    broker_orders: list[BrokerOrder]
    fills: list[ExecutionFill]
    state: ExecutionState


def risk_adjust_portfolio_targets(
    targets: Sequence[PortfolioTargetContract],
    policy: ExecutionPolicy,
) -> list[RiskAdjustedTarget]:
    if not targets:
        return []

    seen: set[str] = set()
    adjusted: list[tuple[PortfolioTargetContract, float, list[str]]] = []

    for target in targets:
        symbol = target.symbol.upper()
        if symbol in seen:
            raise ValueError(f"duplicate target symbol: {symbol}")
        seen.add(symbol)

        weight = float(target.target_weight)
        if not math.isfinite(weight):
            raise ValueError(f"non-finite target weight for {symbol}")

        reasons: list[str] = []
        if policy.long_only and weight < 0:
            weight = 0.0
            reasons.append("LONG_ONLY_FLOOR")

        if abs(weight) > policy.max_symbol_weight:
            weight = math.copysign(policy.max_symbol_weight, weight)
            reasons.append("MAX_SYMBOL_WEIGHT")

        adjusted.append((target, weight, reasons))

    gross = sum(abs(weight) for _, weight, _ in adjusted)
    scale = policy.max_gross_weight / gross if gross > policy.max_gross_weight else 1.0

    out: list[RiskAdjustedTarget] = []
    for target, weight, reasons in adjusted:
        if scale < 1.0:
            weight *= scale
            reasons.append("MAX_GROSS_WEIGHT")
        out.append(
            RiskAdjustedTarget(
                target_id=target.target_id,
                run_id=target.run_id,
                strategy_version=target.strategy_version,
                symbol=target.symbol,
                decision_ts=target.decision_ts,
                effective_ts=target.effective_ts,
                original_weight=float(target.target_weight),
                adjusted_weight=float(weight),
                risk_reason="|".join(reasons) if reasons else "UNCHANGED",
                source=target.source,
            )
        )

    return out


def mark_to_market_equity(
    state: ExecutionState,
    prices: Mapping[str, float],
) -> float:
    equity = float(state.cash)
    for symbol, quantity in state.positions.items():
        if abs(quantity) <= 1e-12:
            continue
        if symbol not in prices:
            raise KeyError(f"missing price for open position {symbol}")
        price = float(prices[symbol])
        if not math.isfinite(price) or price <= 0:
            raise ValueError(f"invalid price for {symbol}")
        equity += float(quantity) * price
    return float(equity)


def build_order_intents(
    targets: Sequence[RiskAdjustedTarget],
    *,
    state: ExecutionState,
    prices: Mapping[str, float],
    equity: float,
    mode: Mode,
    policy: ExecutionPolicy,
) -> list[OrderIntent]:
    if equity <= 0 or not math.isfinite(equity):
        raise ValueError("equity must be finite and > 0")

    intents: list[OrderIntent] = []
    for target in targets:
        symbol = target.symbol.upper()
        if symbol not in prices:
            raise KeyError(f"missing reference price for {symbol}")

        price = float(prices[symbol])
        if not math.isfinite(price) or price <= 0:
            raise ValueError(f"invalid reference price for {symbol}")

        current_quantity = float(state.positions.get(symbol, 0.0))
        target_notional = float(equity) * float(target.adjusted_weight)
        target_quantity = target_notional / price
        delta_quantity = target_quantity - current_quantity
        notional = abs(delta_quantity * price)

        if notional < policy.min_order_notional or abs(delta_quantity) <= 1e-12:
            continue

        side = "BUY" if delta_quantity > 0 else "SELL"
        quantity = abs(delta_quantity)
        risk_reducing = (
            side == "SELL"
            and current_quantity > 0
            and target_quantity < current_quantity
        )

        payload = {
            "target_id": target.target_id,
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "reference_price": price,
            "effective_ts": target.effective_ts,
            "mode": mode.value,
        }
        intents.append(
            OrderIntent(
                intent_id=_stable_id("oi", payload),
                target_id=target.target_id,
                run_id=target.run_id,
                strategy_version=target.strategy_version,
                symbol=symbol,
                side=side,
                quantity=float(quantity),
                current_quantity=float(current_quantity),
                target_quantity=float(target_quantity),
                reference_price=float(price),
                notional=float(notional),
                decision_ts=target.decision_ts,
                effective_ts=target.effective_ts,
                risk_reducing=bool(risk_reducing),
                mode=mode.value,
            )
        )

    return intents


def risk_gate_order_intents(
    intents: Sequence[OrderIntent],
    *,
    equity: float,
    mode: Mode,
    policy: ExecutionPolicy,
) -> list[GatedOrderIntent]:
    if equity <= 0:
        raise ValueError("equity must be > 0")

    turnover_used = 0.0
    max_single = equity * policy.max_single_order_fraction
    max_turnover = equity * policy.max_total_turnover_fraction
    decisions: list[GatedOrderIntent] = []

    ordered = sorted(
        intents,
        key=lambda item: (not item.risk_reducing, item.intent_id),
    )

    for intent in ordered:
        if mode == Mode.LIVE and not policy.allow_live_execution:
            decisions.append(
                GatedOrderIntent(
                    intent=intent,
                    status="REJECTED",
                    risk_reason="LIVE_EXECUTION_DISABLED",
                )
            )
            continue

        if intent.notional > max_single and not intent.risk_reducing:
            decisions.append(
                GatedOrderIntent(
                    intent=intent,
                    status="REJECTED",
                    risk_reason="MAX_SINGLE_ORDER_FRACTION",
                )
            )
            continue

        if (
            not intent.risk_reducing
            and turnover_used + intent.notional > max_turnover
        ):
            decisions.append(
                GatedOrderIntent(
                    intent=intent,
                    status="REJECTED",
                    risk_reason="MAX_TOTAL_TURNOVER_FRACTION",
                )
            )
            continue

        if not intent.risk_reducing:
            turnover_used += intent.notional

        decisions.append(
            GatedOrderIntent(
                intent=intent,
                status="APPROVED",
                risk_reason=(
                    "RISK_REDUCING_EXIT"
                    if intent.risk_reducing
                    else "OK"
                ),
            )
        )

    return sorted(decisions, key=lambda item: item.intent.intent_id)


def plan_shadow_broker_orders(
    gated_intents: Sequence[GatedOrderIntent],
    *,
    policy: ExecutionPolicy,
) -> list[BrokerOrder]:
    if policy.broker.upper() != "SHADOW":
        raise RuntimeError("only SHADOW broker is implemented in execution contract v1")

    orders: list[BrokerOrder] = []
    for gated in gated_intents:
        if gated.status != "APPROVED":
            continue
        intent = gated.intent
        payload = {
            "intent_id": intent.intent_id,
            "symbol": intent.symbol,
            "side": intent.side,
            "quantity": intent.quantity,
            "effective_ts": intent.effective_ts,
            "broker": "SHADOW",
        }
        digest = stable_hash(payload)
        orders.append(
            BrokerOrder(
                broker_order_id=f"bo-{digest[:20]}",
                client_order_id=f"kal-{digest[:28]}",
                intent_id=intent.intent_id,
                symbol=intent.symbol,
                side=intent.side,
                quantity=float(intent.quantity),
                order_type="MARKET",
                time_in_force="DAY",
                broker="SHADOW",
                status="SHADOW_ACCEPTED",
                effective_ts=intent.effective_ts,
                mode=intent.mode,
            )
        )
    return orders


def simulate_shadow_fills(
    orders: Sequence[BrokerOrder],
    *,
    fill_prices: Mapping[str, float],
    fill_ts: str,
    policy: ExecutionPolicy,
) -> list[ExecutionFill]:
    fills: list[ExecutionFill] = []

    for order in orders:
        if order.broker != "SHADOW":
            raise RuntimeError("non-SHADOW broker order reached shadow fill simulator")
        if order.symbol not in fill_prices:
            raise KeyError(f"missing fill price for {order.symbol}")

        raw_price = float(fill_prices[order.symbol])
        if not math.isfinite(raw_price) or raw_price <= 0:
            raise ValueError(f"invalid fill price for {order.symbol}")

        direction = 1.0 if order.side == "BUY" else -1.0
        fill_price = raw_price * (
            1.0 + direction * policy.slippage_bps / 10_000.0
        )
        notional = float(order.quantity) * fill_price
        fee = abs(notional) * policy.commission_bps / 10_000.0
        payload = {
            "broker_order_id": order.broker_order_id,
            "fill_ts": fill_ts,
            "quantity": order.quantity,
            "fill_price": fill_price,
        }
        fills.append(
            ExecutionFill(
                fill_id=_stable_id("fill", payload),
                broker_order_id=order.broker_order_id,
                intent_id=order.intent_id,
                symbol=order.symbol,
                side=order.side,
                quantity=float(order.quantity),
                fill_price=float(fill_price),
                fee=float(fee),
                fill_ts=fill_ts,
                broker="SHADOW",
                status="FILLED",
            )
        )

    return fills


def cash_constrain_shadow_fills(
    state: ExecutionState,
    fills: Sequence[ExecutionFill],
) -> list[ExecutionFill]:
    """Apply available-cash constraints after fill prices are known.

    Planning uses pre-effective prices while fills can occur at a different NAV.
    Risk-reducing SELL fills are applied first to release cash. BUY fills are then
    truncated deterministically when their fill-price cost exceeds remaining
    cash. This prevents a gap move from creating negative cash in SHADOW mode.
    """
    cash = float(state.cash)
    positions = {
        symbol.upper(): float(quantity)
        for symbol, quantity in state.positions.items()
    }
    constrained: list[ExecutionFill] = []

    sells = sorted(
        (fill for fill in fills if fill.side == "SELL"),
        key=lambda fill: fill.fill_id,
    )
    buys = sorted(
        (fill for fill in fills if fill.side == "BUY"),
        key=lambda fill: fill.fill_id,
    )
    unknown = [fill for fill in fills if fill.side not in {"BUY", "SELL"}]
    if unknown:
        raise ValueError(f"unsupported fill side: {unknown[0].side}")

    for fill in sells:
        symbol = fill.symbol.upper()
        current = float(positions.get(symbol, 0.0))
        quantity = float(fill.quantity)
        if quantity > current + 1e-9:
            raise RuntimeError(
                f"shadow fill would oversell {symbol}: {quantity} > {current}"
            )
        positions[symbol] = current - quantity
        if abs(positions[symbol]) <= 1e-10:
            positions.pop(symbol, None)
        cash += quantity * float(fill.fill_price) - float(fill.fee)
        constrained.append(fill)

    for fill in buys:
        desired_quantity = float(fill.quantity)
        price = float(fill.fill_price)
        desired_notional = desired_quantity * price
        fee_rate = (
            float(fill.fee) / desired_notional
            if desired_notional > 0
            else 0.0
        )
        unit_cost = price * (1.0 + fee_rate)
        affordable_quantity = cash / unit_cost if unit_cost > 0 else 0.0
        actual_quantity = min(desired_quantity, max(0.0, affordable_quantity))

        if actual_quantity <= 1e-12:
            continue

        actual_fee = actual_quantity * price * fee_rate
        status = (
            "FILLED"
            if math.isclose(actual_quantity, desired_quantity, rel_tol=1e-12, abs_tol=1e-12)
            else "PARTIALLY_FILLED"
        )
        payload = {
            "broker_order_id": fill.broker_order_id,
            "fill_ts": fill.fill_ts,
            "quantity": actual_quantity,
            "fill_price": price,
            "status": status,
        }
        actual_fill = replace(
            fill,
            fill_id=_stable_id("fill", payload),
            quantity=float(actual_quantity),
            fee=float(actual_fee),
            status=status,
        )
        constrained.append(actual_fill)
        cash -= actual_quantity * price + actual_fee
        if abs(cash) <= 1e-7:
            cash = 0.0

    return sorted(
        constrained,
        key=lambda fill: (fill.side != "SELL", fill.fill_id),
    )


def apply_execution_fills(
    state: ExecutionState,
    fills: Sequence[ExecutionFill],
    *,
    enforce_cash: bool = True,
) -> ExecutionState:
    cash = float(state.cash)
    positions = {symbol.upper(): float(qty) for symbol, qty in state.positions.items()}

    ordered = sorted(fills, key=lambda fill: (fill.side != "SELL", fill.fill_id))
    for fill in ordered:
        symbol = fill.symbol.upper()
        quantity = float(fill.quantity)
        notional = quantity * float(fill.fill_price)

        if fill.side == "SELL":
            current = float(positions.get(symbol, 0.0))
            if quantity > current + 1e-9:
                raise RuntimeError(
                    f"shadow fill would oversell {symbol}: {quantity} > {current}"
                )
            positions[symbol] = current - quantity
            cash += notional - float(fill.fee)
        elif fill.side == "BUY":
            total = notional + float(fill.fee)
            if enforce_cash and total > cash + 1e-7:
                raise RuntimeError(
                    f"insufficient shadow cash for {symbol}: {total} > {cash}"
                )
            positions[symbol] = float(positions.get(symbol, 0.0)) + quantity
            cash -= total
        else:
            raise ValueError(f"unsupported fill side: {fill.side}")

        if abs(positions.get(symbol, 0.0)) <= 1e-10:
            positions.pop(symbol, None)

    if abs(cash) <= 1e-7:
        cash = 0.0
    return ExecutionState(cash=float(cash), positions=positions)


def run_shadow_rebalance(
    targets: Sequence[PortfolioTargetContract],
    *,
    state: ExecutionState,
    planning_prices: Mapping[str, float],
    fill_prices: Mapping[str, float],
    fill_ts: str,
    policy: ExecutionPolicy | None = None,
    mode: Mode = Mode.SHADOW,
) -> ExecutionCycleResult:
    cfg = policy or ExecutionPolicy()

    adjusted = risk_adjust_portfolio_targets(targets, cfg)
    equity = mark_to_market_equity(state, planning_prices)
    intents = build_order_intents(
        adjusted,
        state=state,
        prices=planning_prices,
        equity=equity,
        mode=mode,
        policy=cfg,
    )
    gated = risk_gate_order_intents(
        intents,
        equity=equity,
        mode=mode,
        policy=cfg,
    )

    if mode == Mode.LIVE and cfg.allow_live_execution:
        raise RuntimeError(
            "LIVE broker adapter is intentionally not implemented in execution contract v1"
        )

    orders = plan_shadow_broker_orders(gated, policy=cfg)
    raw_fills = simulate_shadow_fills(
        orders,
        fill_prices=fill_prices,
        fill_ts=fill_ts,
        policy=cfg,
    )
    fills = cash_constrain_shadow_fills(state, raw_fills)
    new_state = apply_execution_fills(state, fills)

    return ExecutionCycleResult(
        adjusted_targets=adjusted,
        gated_intents=gated,
        broker_orders=orders,
        fills=fills,
        state=new_state,
    )
