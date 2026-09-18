package com.hackathon.orders;

import com.hackathon.orders.model.Order;
import com.hackathon.orders.model.OrderItem;
import com.hackathon.orders.service.DiscountService;
import com.hackathon.orders.service.InventoryService;
import com.hackathon.orders.service.OrderProcessor;

public class Main {

    public static void main(String[] args) {
        InventoryService inventoryService = new InventoryService();
        inventoryService.setStock("WIDGET-1", 100);

        Order order = new Order("customer-42");
        order.addItem(new OrderItem("WIDGET-1", 10.0, 5));

        OrderProcessor processor = new OrderProcessor(inventoryService, new DiscountService());
        OrderProcessor.OrderResult result = processor.processOrder(order);

        if (result.isAccepted()) {
            System.out.printf("Order accepted. Total: %.2f%n", result.getTotal());
        } else {
            System.out.println("Order rejected: " + result.getReason());
        }
    }
}
