package com.androidperformance.memorylab;

public class LeakyServiceHolder {
    private final String name;
    private final byte[] payload;

    public LeakyServiceHolder(String name, int payloadKb) {
        this.name = name;
        this.payload = new byte[Math.max(payloadKb, 1) * 1024];
        if (this.payload.length > 0) {
            this.payload[0] = (byte) name.length();
        }
    }

    public String getName() {
        return name;
    }
}
