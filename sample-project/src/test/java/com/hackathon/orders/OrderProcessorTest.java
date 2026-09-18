package com.hackathon.orders;

import com.hackathon.orders.model.Customer;
import com.hackathon.orders.model.LoyaltyTier;
import com.hackathon.orders.model.Order;
import com.hackathon.orders.model.OrderItem;
import com.hackathon.orders.service.CustomerService;
import com.hackathon.orders.service.DiscountService;
import com.hackathon.orders.service.InventoryService;
import com.hackathon.orders.service.LoyaltyService;
import com.hackathon.orders.service.OrderProcessor;
import com.hackathon.orders.service.ShippingService;
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
        // bulk-order threshold and receive a 10% discount -> 135.0.
        // Guest customer (unregistered) gets no loyalty discount, so only
        // shipping (4.99 + 3 * 0.50 = 6.49) is added on top -> 141.49.
        order.addItem(new OrderItem("WIDGET-1", 10.0, 5));
        order.addItem(new OrderItem("WIDGET-2", 10.0, 5));
        order.addItem(new OrderItem("WIDGET-3", 10.0, 5));

        OrderProcessor processor = new OrderProcessor(
                inventoryService,
                new DiscountService(),
                new CustomerService(),
                new LoyaltyService(),
                new ShippingService());
        OrderProcessor.OrderResult result = processor.processOrder(order);

        assertTrue(result.isAccepted());
        assertEquals(141.49, result.getTotal(), 0.001,
                "Order subtotal of 150.0 should trigger the bulk discount (135.0), "
                        + "plus shipping (6.49) for a guest customer with no loyalty discount");
    }

    @Test
    void platinumCustomerGetsTenPercentLoyaltyDiscount() {
        InventoryService inventoryService = new InventoryService();
        inventoryService.setStock("WIDGET-1", 100);

        CustomerService customerService = new CustomerService();
        customerService.registerCustomer(new Customer("cust-platinum", "Dana Platinum", LoyaltyTier.PLATINUM));

        Order order = new Order("cust-platinum");
        // Subtotal = 50.0, below the bulk discount threshold, so only the
        // PLATINUM loyalty discount (10%) applies -> 45.0, plus shipping
        // (4.99 + 1 * 0.50 = 5.49) -> 50.49.
        order.addItem(new OrderItem("WIDGET-1", 50.0, 1));

        OrderProcessor processor = new OrderProcessor(
                inventoryService,
                new DiscountService(),
                customerService,
                new LoyaltyService(),
                new ShippingService());
        OrderProcessor.OrderResult result = processor.processOrder(order);

        assertTrue(result.isAccepted());
        assertEquals(50.49, result.getTotal(), 0.001,
                "PLATINUM customers should get a 10% loyalty discount, not 5%");
    }
}
