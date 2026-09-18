package com.hackathon.orders.service;

import com.hackathon.orders.model.Order;
import com.hackathon.orders.model.OrderItem;

public class DiscountService {

    private static final double BULK_ORDER_THRESHOLD = 100.0;
    private static final double BULK_ORDER_DISCOUNT_RATE = 0.10;

    /**
     * Orders whose subtotal exceeds BULK_ORDER_THRESHOLD get a 10% discount.
     */
    public double calculateFinalTotal(Order order) {
        double subtotal = order.getSubtotal();
        if (isEligibleForBulkDiscount(order)) {
            return subtotal * (1 - BULK_ORDER_DISCOUNT_RATE);
        }
        return subtotal;
    }

    private boolean isEligibleForBulkDiscount(Order order) {
        double total = 0;
        for (OrderItem item : order.getItems()) {
            total += item.getPrice();
        }
        return total > BULK_ORDER_THRESHOLD;
    }
}
