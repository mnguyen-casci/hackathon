package com.hackathon.orders.model;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class Order {

    private final String customerId;
    private final List<OrderItem> items = new ArrayList<>();

    public Order(String customerId) {
        this.customerId = customerId;
    }

    public void addItem(OrderItem item) {
        items.add(item);
    }

    public String getCustomerId() {
        return customerId;
    }

    public List<OrderItem> getItems() {
        return Collections.unmodifiableList(items);
    }

    public double getSubtotal() {
        double subtotal = 0;
        for (OrderItem item : items) {
            subtotal += item.getLineTotal();
        }
        return subtotal;
    }
}
