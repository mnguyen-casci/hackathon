package com.hackathon.orders.service;

import com.hackathon.orders.model.Customer;
import com.hackathon.orders.model.Order;

public class OrderProcessor {

    private final InventoryService inventoryService;
    private final DiscountService discountService;
    private final CustomerService customerService;
    private final LoyaltyService loyaltyService;
    private final ShippingService shippingService;

    public OrderProcessor(
            InventoryService inventoryService,
            DiscountService discountService,
            CustomerService customerService,
            LoyaltyService loyaltyService,
            ShippingService shippingService) {
        this.inventoryService = inventoryService;
        this.discountService = discountService;
        this.customerService = customerService;
        this.loyaltyService = loyaltyService;
        this.shippingService = shippingService;
    }

    public OrderResult processOrder(Order order) {
        if (!inventoryService.hasSufficientStock(order)) {
            return OrderResult.rejected("Insufficient stock");
        }
        double afterBulkDiscount = discountService.calculateFinalTotal(order);

        Customer customer = customerService.getCustomer(order.getCustomerId());
        double afterLoyaltyDiscount = loyaltyService.applyLoyaltyDiscount(customer, afterBulkDiscount);

        double shippingCost = shippingService.calculateShippingCost(order);
        double grandTotal = afterLoyaltyDiscount + shippingCost;

        return OrderResult.accepted(grandTotal);
    }

    public static class OrderResult {
        private final boolean accepted;
        private final String reason;
        private final double total;

        private OrderResult(boolean accepted, String reason, double total) {
            this.accepted = accepted;
            this.reason = reason;
            this.total = total;
        }

        public static OrderResult accepted(double total) {
            return new OrderResult(true, null, total);
        }

        public static OrderResult rejected(String reason) {
            return new OrderResult(false, reason, 0);
        }

        public boolean isAccepted() {
            return accepted;
        }

        public String getReason() {
            return reason;
        }

        public double getTotal() {
            return total;
        }
    }
}
