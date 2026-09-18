# orders — architecture summary

Small order-processing service. Maven/Java 21, JUnit 5 for tests.

## Module map

- `model/Order.java` — an order: customer id + list of `OrderItem`.
  `getSubtotal()` sums each item's `price * quantity`.
- `model/OrderItem.java` — a single line item: sku, unit price, quantity.
  `getLineTotal()` = `price * quantity`.
- `service/InventoryService.java` — tracks stock by sku, checks whether an
  order can be fulfilled. Unrelated to pricing/discount logic.
- `service/DiscountService.java` — applies a 10% bulk-order discount when an
  order's total exceeds a $100 threshold.
- `service/OrderProcessor.java` — orchestrates: checks inventory via
  `InventoryService`, then prices the order via `DiscountService`.
- `Main.java` — demo entry point, not exercised by tests.

## Conventions

- Services are stateless except `InventoryService`'s in-memory stock map.
- Money amounts are `double`, no currency rounding is applied.
- Any change to pricing logic must keep `mvn test` passing — the test suite
  is the source of truth for expected totals.

## Verifying changes

```
mvn test
```
