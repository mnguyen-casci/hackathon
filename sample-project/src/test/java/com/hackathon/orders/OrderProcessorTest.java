package com.hackathon.orders;

import com.hackathon.orders.model.Order;
import com.hackathon.orders.model.OrderItem;
import com.hackathon.orders.service.DiscountService;
import com.hackathon.orders.service.InventoryService;
import com.hackathon.orders.service.OrderProcessor;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class OrderProcessorTest {

    @Test
    void bulkOrderWithLowUnitPriceButHighQuantityGetsDiscount() {
        InventoryService inventoryService = new InventoryService();
        inventoryService.setStock("WIDGET-1", 100);
        inventoryService.setStock("WIDGET-2", 100);
        inventoryService.setStock("WIDGET-3", 100);

        Order order = new Order("customer-1");
        // Subtotal = 3 * (10.0 * 5) = 150.0, which should exceed the 100.0
        // bulk-order threshold and receive a 10% discount -> 135.0
        order.addItem(new OrderItem("WIDGET-1", 10.0, 5));
        order.addItem(new OrderItem("WIDGET-2", 10.0, 5));
        order.addItem(new OrderItem("WIDGET-3", 10.0, 5));

        OrderProcessor processor = new OrderProcessor(inventoryService, new DiscountService());
        OrderProcessor.OrderResult result = processor.processOrder(order);

        assertTrue(result.isAccepted());
        assertEquals(135.0, result.getTotal(), 0.001,
                "Order subtotal of 150.0 should trigger the bulk discount and total 135.0");
    }
}
