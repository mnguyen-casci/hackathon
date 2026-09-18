package com.hackathon.orders.model;

public class OrderItem {

    private final String sku;
    private final double price;
    private final int quantity;

    public OrderItem(String sku, double price, int quantity) {
        this.sku = sku;
        this.price = price;
        this.quantity = quantity;
    }

    public String getSku() {
        return sku;
    }

    public double getPrice() {
        return price;
    }

    public int getQuantity() {
        return quantity;
    }

    public double getLineTotal() {
        return price * quantity;
    }
}
