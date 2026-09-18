package com.hackathon.orders.service;

import com.hackathon.orders.model.Order;

public class OrderProcessor {

    private final InventoryService inventoryService;
    private final DiscountService discountService;

    public OrderProcessor(InventoryService inventoryService, DiscountService discountService) {
        this.inventoryService = inventoryService;
        this.discountService = discountService;
    }

    public OrderResult processOrder(Order order) {
        if (!inventoryService.hasSufficientStock(order)) {
            return OrderResult.rejected("Insufficient stock");
        }
        double total = discountService.calculateFinalTotal(order);
        return OrderResult.accepted(total);
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
