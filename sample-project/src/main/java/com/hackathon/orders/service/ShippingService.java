package com.hackathon.orders.service;

import com.hackathon.orders.model.Order;
import com.hackathon.orders.model.ShippingAddress;

public class ShippingService {

    private static final double BASE_RATE = 4.99;
    private static final double PER_ITEM_RATE = 0.50;
    private static final double INTERNATIONAL_SURCHARGE = 12.00;
    private static final double EXPEDITED_SURCHARGE = 8.00;

    public double calculateShippingCost(Order order) {
        int itemCount = order.getItems().size();
        double cost = BASE_RATE + (itemCount * PER_ITEM_RATE);

        ShippingAddress address = order.getShippingAddress();
        if (address != null) {
            if (!"US".equals(address.getCountry())) {
                cost += INTERNATIONAL_SURCHARGE;
            }
            if (address.isExpedited()) {
                cost += EXPEDITED_SURCHARGE;
            }
        }
        return cost;
    }
}
