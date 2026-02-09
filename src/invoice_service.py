from dataclasses import dataclass
from typing import List, Optional, Dict, Tuple


@dataclass
class LineItem:
    sku: str
    category: str
    unit_price: float
    qty: int
    fragile: bool = False


@dataclass
class Invoice:
    invoice_id: str
    customer_id: str
    country: str
    membership: str
    coupon: Optional[str]
    items: List[LineItem]


class InvoiceService:
    # ---- Constants / Config ----
    ALLOWED_CATEGORIES = {"book", "food", "electronics", "other"}

    FRAGILE_FEE_PER_UNIT = 5.0

    SHIPPING_RULES = {
        # country: [(threshold, shipping_fee_if_subtotal_lt_threshold), ...] last match falls through to 0
        "TH": [(500, 60)],
        "JP": [(4000, 600)],
        "US": [(100, 15), (300, 8)],
        "DEFAULT": [(200, 25)],
    }

    TAX_RATE = {
        "TH": 0.07,
        "JP": 0.10,
        "US": 0.08,
        "DEFAULT": 0.05,
    }

    MEMBERSHIP_DISCOUNT_RATE = {
        "gold": 0.03,
        "platinum": 0.05,
    }

    NON_MEMBER_BULK_THRESHOLD = 3000
    NON_MEMBER_BULK_DISCOUNT = 20.0

    UPGRADE_HINT_THRESHOLD = 10000

    def __init__(self) -> None:
        self._coupon_rate: Dict[str, float] = {
            "WELCOME10": 0.10,
            "VIP20": 0.20,
            "STUDENT5": 0.05,
        }

    # ---------- Public API ----------
    def compute_total(self, inv: Invoice) -> Tuple[float, List[str]]:
        warnings: List[str] = []

        self._validate_or_raise(inv)

        subtotal = self._subtotal(inv.items)
        fragile_fee = self._fragile_fee(inv.items)
        shipping = self._shipping_fee(inv.country, subtotal)

        discount = self._discount(inv, subtotal, warnings)
        tax = self._tax(inv.country, subtotal - discount)

        total = subtotal + shipping + fragile_fee + tax - discount
        total = max(total, 0.0)

        self._append_warnings(inv, subtotal, warnings)

        return total, warnings

    # ---------- Validation ----------
    def _validate_or_raise(self, inv: Invoice) -> None:
        problems = self._validate(inv)
        if problems:
            raise ValueError("; ".join(problems))

    def _validate(self, inv: Invoice) -> List[str]:
        problems: List[str] = []
        if inv is None:
            return ["Invoice is missing"]

        if not inv.invoice_id:
            problems.append("Missing invoice_id")
        if not inv.customer_id:
            problems.append("Missing customer_id")
        if not inv.items:
            problems.append("Invoice must contain items")
            return problems  # no need to check items if empty

        for it in inv.items:
            if not it.sku:
                problems.append("Item sku is missing")
            if it.qty <= 0:
                problems.append(f"Invalid qty for {it.sku}")
            if it.unit_price < 0:
                problems.append(f"Invalid price for {it.sku}")
            if it.category not in self.ALLOWED_CATEGORIES:
                problems.append(f"Unknown category for {it.sku}")

        return problems

    # ---------- Calculations ----------
    def _subtotal(self, items: List[LineItem]) -> float:
        return sum(it.unit_price * it.qty for it in items)

    def _fragile_fee(self, items: List[LineItem]) -> float:
        return sum(self.FRAGILE_FEE_PER_UNIT * it.qty for it in items if it.fragile)

    def _shipping_fee(self, country: str, subtotal: float) -> float:
        rules = self.SHIPPING_RULES.get(country, self.SHIPPING_RULES["DEFAULT"])
        for threshold, fee in rules:
            if subtotal < threshold:
                return float(fee)
        return 0.0

    def _discount(self, inv: Invoice, subtotal: float, warnings: List[str]) -> float:
        discount = 0.0

        # membership discount
        rate = self.MEMBERSHIP_DISCOUNT_RATE.get(inv.membership)
        if rate is not None:
            discount += subtotal * rate
        else:
            # non-member bulk discount
            if subtotal > self.NON_MEMBER_BULK_THRESHOLD:
                discount += self.NON_MEMBER_BULK_DISCOUNT

        # coupon discount
        code = (inv.coupon or "").strip()
        if code:
            rate = self._coupon_rate.get(code)
            if rate is None:
                warnings.append("Unknown coupon")
            else:
                discount += subtotal * rate

        return discount

    def _tax(self, country: str, taxable_amount: float) -> float:
        rate = self.TAX_RATE.get(country, self.TAX_RATE["DEFAULT"])
        taxable_amount = max(taxable_amount, 0.0)
        return taxable_amount * rate

    # ---------- Warnings ----------
    def _append_warnings(self, inv: Invoice, subtotal: float, warnings: List[str]) -> None:
        if subtotal > self.UPGRADE_HINT_THRESHOLD and inv.membership not in self.MEMBERSHIP_DISCOUNT_RATE:
            warnings.append("Consider membership upgrade")
