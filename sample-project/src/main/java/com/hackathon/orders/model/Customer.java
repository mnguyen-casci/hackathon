package com.hackathon.orders.model;

public class Customer {

    private final String customerId;
    private final String name;
    private final LoyaltyTier loyaltyTier;

    public Customer(String customerId, String name, LoyaltyTier loyaltyTier) {
        this.customerId = customerId;
        this.name = name;
        this.loyaltyTier = loyaltyTier;
    }

    public String getCustomerId() {
        return customerId;
    }

    public String getName() {
        return name;
    }

    public LoyaltyTier getLoyaltyTier() {
        return loyaltyTier;
    }
}
