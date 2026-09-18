package com.hackathon.orders.model;

public class ShippingAddress {

    private final String country;
    private final boolean expedited;

    public ShippingAddress(String country, boolean expedited) {
        this.country = country;
        this.expedited = expedited;
    }

    public String getCountry() {
        return country;
    }

    public boolean isExpedited() {
        return expedited;
    }
}
