# Sample project: order processing

A small Maven/Java service used as the fixture for the context-optimization
benchmark. It has one deliberate, cross-file bug.

## The task

`mvn test` currently fails. Find and fix the bug so it passes, without
changing the test.

## Structure

- `model/Order.java`, `model/OrderItem.java` — order data, `Order.getSubtotal()`
  correctly sums `price * quantity` per line item.
- `service/InventoryService.java` — stock checks (not related to the bug).
- `service/DiscountService.java` — applies a 10% discount to orders whose
  subtotal exceeds a $100 threshold.
- `service/OrderProcessor.java` — orchestrates inventory + discount checks.

## Verifying a fix

```
mvn test
```

Passes once the bug is fixed.
