"""Non-invasive order fulfillment ledger for the AMFO closed-loop supply-chain model.

Quantities are converted to RTIs on registration so that UL-based pooler orders
and RTI-based producer orders can be compared in the same units. Each order's
original quantity is retained independently of the mutable OrderLine.quantity.
"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class TrackedOrder:
    order_id: str
    stream: str
    issuer: str
    supplier: str
    crate_type: str
    creation_step: int
    due_step: int
    original_quantity: int
    uom: str
    original_rtis: int
    on_time_rtis: int = 0
    late_rtis: int = 0
    last_delivery_step: Optional[int] = None

    @property
    def fulfilled_rtis(self) -> int:
        return self.on_time_rtis + self.late_rtis

    @property
    def outstanding_rtis(self) -> int:
        return self.original_rtis - self.fulfilled_rtis


class OrderTracker:
    """Records deliveries at the receiving node, without changing model decisions."""

    STREAMS = ('producer', 'pooler')
    STAT_NAMES = (
        'created_rtis', 'due_rtis', 'on_time_rtis', 'late_rtis',
        'outstanding_due_rtis', 'not_yet_due_rtis',
        'due_today_rtis', 'on_time_due_today_rtis',
        'on_time_fill_rate_pct', 'due_today_fill_rate_pct',
    )

    def __init__(self, ul_size: int):
        if ul_size <= 0:
            raise ValueError('UL size must be positive')
        self.ul_size = ul_size
        self.orders: dict[str, TrackedOrder] = {}

    def register(self, order) -> None:
        if order.order_id in self.orders:
            raise ValueError(f'Duplicate order id: {order.order_id}')
        if order.uom not in ('RTI', 'UL'):
            raise ValueError(f'Unexpected order unit: {order.uom}')
        if order.quantity < 0 or order.lead_time < 0:
            raise ValueError('Negative order quantity or lead time')
        multiplier = self.ul_size if order.uom == 'UL' else 1
        self.orders[order.order_id] = TrackedOrder(
            order_id=order.order_id,
            stream='pooler' if order.uom == 'UL' else 'producer',
            issuer=order.issuer,
            supplier=order.supplier,
            crate_type=order.crate_type.name,
            creation_step=order.creation_step,
            due_step=order.creation_step + order.lead_time,
            original_quantity=order.quantity,
            uom=order.uom,
            original_rtis=order.quantity * multiplier,
        )

    def deliver(self, order, delivered_quantity: int, step: int) -> None:
        """Record actual amount delivered, in the order's original unit of measure."""
        record = self.orders[order.order_id]
        if delivered_quantity < 0:
            raise ValueError('Negative delivered quantity')
        if delivered_quantity == 0:
            return
        if step < record.due_step:
            raise ValueError('Unexpected early delivery; check baseline semantics')
        multiplier = self.ul_size if record.uom == 'UL' else 1
        delivered_rtis = delivered_quantity * multiplier
        if delivered_rtis > record.outstanding_rtis:
            raise ValueError('Delivery exceeds outstanding order quantity')
        if step == record.due_step:
            record.on_time_rtis += delivered_rtis
        else:
            record.late_rtis += delivered_rtis
        record.last_delivery_step = step

    def snapshot(self, step: int) -> dict[str, float | int | None]:
        result = {}
        for stream in self.STREAMS:
            selected = [o for o in self.orders.values() if o.stream == stream]
            due = [o for o in selected if o.due_step <= step]
            due_today = [o for o in selected if o.due_step == step]
            created_qty = sum(o.original_rtis for o in selected)
            due_qty = sum(o.original_rtis for o in due)
            on_time = sum(o.on_time_rtis for o in due)
            late = sum(o.late_rtis for o in due)
            overdue = sum(o.outstanding_rtis for o in due)
            not_yet_due = sum(o.outstanding_rtis for o in selected if o.due_step > step)
            due_today_qty = sum(o.original_rtis for o in due_today)
            due_today_ontime = sum(o.on_time_rtis for o in due_today)
            data = {
                'created_rtis': created_qty,
                'due_rtis': due_qty,
                'on_time_rtis': on_time,
                'late_rtis': late,
                'outstanding_due_rtis': overdue,
                'not_yet_due_rtis': not_yet_due,
                'due_today_rtis': due_today_qty,
                'on_time_due_today_rtis': due_today_ontime,
                'on_time_fill_rate_pct': round(100 * on_time / due_qty, 6) if due_qty else None,
                'due_today_fill_rate_pct': round(100 * due_today_ontime / due_today_qty, 6) if due_today_qty else None,
            }
            result.update({f'{stream}_{key}': value for key, value in data.items()})
        return result

    def audit_rows(self, step: int) -> list[dict]:
        rows = []
        for o in self.orders.values():
            status = 'complete' if o.outstanding_rtis == 0 else ('not_yet_due' if o.due_step > step else 'outstanding_due')
            rows.append({
                'Order ID': o.order_id,
                'Stream': o.stream,
                'Issuer': o.issuer,
                'Supplier': o.supplier,
                'Crate Type': o.crate_type,
                'Created Step': o.creation_step,
                'Due Step': o.due_step,
                'Original Quantity': o.original_quantity,
                'UoM': o.uom,
                'Original RTIs': o.original_rtis,
                'On Time RTIs': o.on_time_rtis,
                'Late RTIs': o.late_rtis,
                'Outstanding RTIs': o.outstanding_rtis,
                'Last Delivery Step': o.last_delivery_step,
                'Status': status,
            })
        return rows
