package com.hackathon.orders.service;

import com.hackathon.orders.model.Order;
import com.hackathon.orders.model.OrderItem;

import java.util.HashMap;
import java.util.Map;

public class InventoryService {

    private final Map<String, Integer> stockBySku = new HashMap<>();

    public void setStock(String sku, int quantity) {
        stockBySku.put(sku, quantity);
    }

    public boolean hasSufficientStock(Order order) {
        for (OrderItem item : order.getItems()) {
            int available = stockBySku.getOrDefault(item.getSku(), 0);
            if (available < item.getQuantity()) {
                return false;
            }
        }
        return true;
    }
}
