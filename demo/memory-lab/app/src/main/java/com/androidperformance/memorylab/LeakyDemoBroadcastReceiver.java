package com.androidperformance.memorylab;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

public class LeakyDemoBroadcastReceiver extends BroadcastReceiver {
    private final byte[] payload;

    public LeakyDemoBroadcastReceiver(int payloadKb) {
        this.payload = new byte[Math.max(payloadKb, 1) * 1024];
        if (this.payload.length > 0) {
            this.payload[0] = 7;
        }
    }

    @Override
    public void onReceive(Context context, Intent intent) {
        if (payload.length > 1) {
            payload[1] = payload[0];
        }
    }
}
