package com.androidperformance.memorylab;

import android.app.Activity;
import android.graphics.Bitmap;
import android.os.SharedMemory;
import android.util.LruCache;
import android.view.View;
import android.webkit.WebView;

import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.List;

public final class LeakySingletons {
    public static final List<Object> JAVA_LEAK_BUCKET = new ArrayList<>();
    public static final List<Bitmap> BITMAP_CACHE = new ArrayList<>();
    public static final List<ByteBuffer> DIRECT_BUFFERS = new ArrayList<>();
    public static final List<SharedMemory> ASHMEM_BUFFERS = new ArrayList<>();
    public static final List<WebView> WEBVIEW_LEAKS = new ArrayList<>();
    public static final List<Thread> EXTRA_THREADS = new ArrayList<>();
    public static final List<Object> LOW_UTIL_COLLECTIONS = new ArrayList<>();
    public static final List<View> VIEW_STORM = new ArrayList<>();
    public static final List<LeakyDemoFragment> FRAGMENT_LEAKS = new ArrayList<>();
    public static final List<LeakyServiceHolder> SERVICE_LEAKS = new ArrayList<>();
    public static final List<LeakyDemoBroadcastReceiver> RECEIVER_LEAKS = new ArrayList<>();
    public static final List<LruCache<String, byte[]>> BUSINESS_LRU_CACHES = new ArrayList<>();

    public static Activity leakedActivity;

    private LeakySingletons() {
    }
}
