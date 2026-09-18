package com.hackathon.orders.util;

public final class CurrencyUtil {

    private CurrencyUtil() {
    }

    public static double round(double amount) {
        return Math.round(amount * 100.0) / 100.0;
    }
}
