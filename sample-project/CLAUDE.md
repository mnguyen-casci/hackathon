# orders — architecture summary

Small order-processing service. Maven/Java 21, JUnit 5 for tests.

## Module map

- `model/Order.java` — an order: customer id, list of `OrderItem`, optional
  `ShippingAddress`. `getSubtotal()` sums each item's `price * quantity`.
- `model/OrderItem.java` — a single line item: sku, unit price, quantity.
  `getLineTotal()` = `price * quantity`.
- `model/Customer.java`, `model/LoyaltyTier.java` — a customer and their
  loyalty tier (`STANDARD`, `GOLD`, `PLATINUM`).
- `model/ShippingAddress.java` — country + expedited flag.
- `service/InventoryService.java` — tracks stock by sku, checks whether an
  order can be fulfilled. Unrelated to pricing/discount logic.
- `service/DiscountService.java` — applies a 10% bulk-order discount when an
  order's total exceeds a $100 threshold.
- `service/CustomerService.java` — looks up a `Customer` by id, defaulting to
  a `STANDARD`-tier guest if the id isn't registered.
- `service/LoyaltyService.java` — applies a loyalty discount on top of the
  bulk discount, based on the customer's tier.
- `service/ShippingService.java` — computes shipping cost from item count and
  address. Unrelated to discount/pricing logic.
- `service/PaymentService.java` — simulated payment processing used
  elsewhere in the wider application. Not called by `OrderProcessor`.
- `service/OrderProcessor.java` — orchestrates the full pipeline: inventory
  check, bulk discount, loyalty discount, shipping cost.
- `Main.java` — demo entry point, not exercised by tests.

## Conventions

- Services are stateless except `InventoryService`'s and `CustomerService`'s
  in-memory maps.
- Money amounts are `double`, no currency rounding is applied.
- Any change to pricing logic must keep `mvn test` passing — the test suite
  is the source of truth for expected totals.

## Verifying changes

```
mvn test
```
