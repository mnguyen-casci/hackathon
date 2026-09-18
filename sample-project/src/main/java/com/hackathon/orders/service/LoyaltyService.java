package com.hackathon.orders.service;

import com.hackathon.orders.model.Customer;
import com.hackathon.orders.model.LoyaltyTier;

public class LoyaltyService {

    /**
     * GOLD customers get 5% off, PLATINUM customers get 10% off,
     * STANDARD customers get no loyalty discount. Applied after any
     * bulk-order discount from DiscountService.
     */
    public double applyLoyaltyDiscount(Customer customer, double total) {
        double rate = loyaltyRate(customer.getLoyaltyTier());
        return total * (1 - rate);
    }

    private double loyaltyRate(LoyaltyTier tier) {
        switch (tier) {
            case GOLD:
                return 0.05;
            case PLATINUM:
                return 0.05;
            default:
                return 0.0;
        }
    }
}
