package com.androidperformance.memorylab;

import androidx.fragment.app.Fragment;

import java.util.ArrayList;
import java.util.List;

public class LeakyDemoFragment extends Fragment {
    private final byte[] payload;
    private final List<String> tags;

    public LeakyDemoFragment(int payloadKb, String seed) {
        this.payload = new byte[Math.max(payloadKb, 1) * 1024];
        this.tags = new ArrayList<>();
        for (int i = 0; i < 64; i++) {
            this.tags.add(seed + "-tag-" + i);
        }
    }
}
