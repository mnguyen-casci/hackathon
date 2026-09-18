package com.hackathon.orders.service;

import com.hackathon.orders.model.Customer;
import com.hackathon.orders.model.LoyaltyTier;

import java.util.HashMap;
import java.util.Map;

public class CustomerService {

    private final Map<String, Customer> customers = new HashMap<>();

    public void registerCustomer(Customer customer) {
        customers.put(customer.getCustomerId(), customer);
    }

    public Customer getCustomer(String customerId) {
        return customers.getOrDefault(
                customerId, new Customer(customerId, "Guest", LoyaltyTier.STANDARD));
    }
}
