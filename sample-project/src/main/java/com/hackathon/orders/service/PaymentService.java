package com.hackathon.orders.service;

public class PaymentService {

    /**
     * Simulated payment processing, used by other parts of the wider
     * application. Not part of the OrderProcessor pipeline.
     */
    public boolean processPayment(String customerId, double amount) {
        if (amount <= 0) {
            return false;
        }
        return true;
    }
}
