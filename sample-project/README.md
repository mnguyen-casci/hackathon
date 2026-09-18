# Sample project: order processing

A small Maven/Java service used as the fixture for the context-optimization
benchmark. It has one deliberate, cross-file bug.

## The task

`mvn test` currently fails. Find and fix the bug so it passes, without
changing the test.

## Structure

- `model/Order.java`, `model/OrderItem.java` — order data, `Order.getSubtotal()`
  correctly sums `price * quantity` per line item.
- `model/Customer.java`, `model/LoyaltyTier.java` — a customer and their
  loyalty tier (`STANDARD`, `GOLD`, `PLATINUM`).
- `model/ShippingAddress.java` — optional shipping details on an order.
- `service/InventoryService.java` — stock checks (not related to the bug).
- `service/DiscountService.java` — applies a 10% bulk-order discount when a
  subtotal exceeds a $100 threshold.
- `service/CustomerService.java` — looks up a `Customer` by id, defaulting to
  a `STANDARD`-tier guest if unregistered.
- `service/LoyaltyService.java` — applies a loyalty discount on top of the
  bulk discount, based on the customer's tier.
- `service/ShippingService.java` — computes shipping cost from item count and
  address (not related to the bug).
- `service/PaymentService.java` — simulated payment processing, used
  elsewhere in the wider application. Not called by `OrderProcessor`.
- `service/OrderProcessor.java` — orchestrates: inventory check, bulk
  discount, loyalty discount, shipping cost.

## Verifying a fix

```
mvn test
```

Passes once the bug is fixed.
