package com.androidperformance.memorylab;

import android.app.Activity;
import android.graphics.Bitmap;
import android.os.Debug;
import android.os.Handler;
import android.os.Looper;
import android.os.Process;
import android.os.SharedMemory;
import android.os.SystemClock;
import android.system.ErrnoException;
import android.util.Log;
import android.util.LruCache;
import android.widget.TextView;
import android.webkit.WebView;

import java.io.File;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.atomic.AtomicBoolean;

public class MemoryScenarioController {

    private static final String TAG = "MemoryLab";

    private final AtomicBoolean threadStop = new AtomicBoolean(false);
    private final Handler mainHandler = new Handler(Looper.getMainLooper());
    private Runnable jankRunnable;
    private volatile double jankSink;

    public void leakActivity(Activity activity) {
        LeakySingletons.leakedActivity = activity;
    }

    public int allocateJavaLeakObjects(int targetMb) {
        int oneChunkKb = 256;
        int chunkCount = (targetMb * 1024) / oneChunkKb;
        for (int i = 0; i < chunkCount; i++) {
            byte[] payload = new byte[oneChunkKb * 1024];
            payload[0] = (byte) (i & 0x7F);
            payload[payload.length - 1] = (byte) ((i + 1) & 0x7F);
            LeakySingletons.JAVA_LEAK_BUCKET.add(payload);
        }
        return chunkCount;
    }

    public int inflateLowUtilizationCollections() {
        int created = 0;
        for (int i = 0; i < 80; i++) {
            Map<String, byte[]> map = new HashMap<>(16384);
            for (int j = 0; j < 90; j++) {
                map.put("item-" + i + "-" + j, new byte[8 * 1024]);
            }
            LeakySingletons.LOW_UTIL_COLLECTIONS.add(map);
            created++;
        }
        for (int i = 0; i < 250; i++) {
            LeakySingletons.LOW_UTIL_COLLECTIONS.add(new ArrayList<>());
            created++;
        }
        return created;
    }

    public int createLeakyFragments(int count, int payloadKb) {
        for (int i = 0; i < count; i++) {
            LeakySingletons.FRAGMENT_LEAKS.add(new LeakyDemoFragment(payloadKb, "fragment-" + i));
        }
        return LeakySingletons.FRAGMENT_LEAKS.size();
    }

    public int createLeakyServices(int count, int payloadKb) {
        for (int i = 0; i < count; i++) {
            LeakySingletons.SERVICE_LEAKS.add(new LeakyServiceHolder("service-" + i, payloadKb));
        }
        return LeakySingletons.SERVICE_LEAKS.size();
    }

    public int createLeakyReceivers(int count, int payloadKb) {
        for (int i = 0; i < count; i++) {
            LeakySingletons.RECEIVER_LEAKS.add(new LeakyDemoBroadcastReceiver(payloadKb));
        }
        return LeakySingletons.RECEIVER_LEAKS.size();
    }

    public int createMisconfiguredLruCaches(int cacheCount) {
        for (int c = 0; c < cacheCount; c++) {
            LruCache<String, byte[]> cache = new LruCache<String, byte[]>(200 * 1024 * 1024) {
                @Override
                protected int sizeOf(String key, byte[] value) {
                    return value.length;
                }
            };

            for (int i = 0; i < 800; i++) {
                cache.put("hit-" + c + "-" + i, new byte[32 * 1024]);
            }
            for (int i = 0; i < 1600; i++) {
                cache.get("miss-" + c + "-" + i);
            }
            for (int i = 0; i < 60; i++) {
                cache.get("hit-" + c + "-" + (i * 13 % 800));
            }
            LeakySingletons.BUSINESS_LRU_CACHES.add(cache);
        }
        return LeakySingletons.BUSINESS_LRU_CACHES.size();
    }

    public int inflateViewStorm(Activity activity, int count) {
        for (int i = 0; i < count; i++) {
            TextView textView = new TextView(activity);
            textView.setText("view-storm-" + i);
            LeakySingletons.VIEW_STORM.add(textView);
        }
        return LeakySingletons.VIEW_STORM.size();
    }

    public int allocateBitmapDuplicates() {
        List<Bitmap> bitmaps = LeakySingletons.BITMAP_CACHE;
        bitmaps.add(Bitmap.createBitmap(2112, 1080, Bitmap.Config.ARGB_8888));
        bitmaps.add(Bitmap.createBitmap(1091, 724, Bitmap.Config.ARGB_8888));
        bitmaps.add(Bitmap.createBitmap(968, 544, Bitmap.Config.ARGB_8888));
        for (int i = 0; i < 18; i++) {
            bitmaps.add(Bitmap.createBitmap(820, 544, Bitmap.Config.ARGB_8888));
        }
        return bitmaps.size();
    }

    public int allocateDirectBuffers(int count, int eachKb) {
        for (int i = 0; i < count; i++) {
            ByteBuffer byteBuffer = ByteBuffer.allocateDirect(eachKb * 1024);
            byteBuffer.putInt(0, i);
            LeakySingletons.DIRECT_BUFFERS.add(byteBuffer);
        }
        return LeakySingletons.DIRECT_BUFFERS.size();
    }

    public int allocateAshmemBlocks(int count, int eachMb) {
        int created = 0;
        for (int i = 0; i < count; i++) {
            try {
                SharedMemory sharedMemory = SharedMemory.create("memory-lab-ashmem-" + i, eachMb * 1024 * 1024);
                ByteBuffer byteBuffer = sharedMemory.mapReadWrite();
                if (byteBuffer.remaining() > 16) {
                    byteBuffer.putInt(0, i);
                    byteBuffer.putInt(4, eachMb);
                }
                LeakySingletons.ASHMEM_BUFFERS.add(sharedMemory);
                created++;
            } catch (ErrnoException | RuntimeException exception) {
                Log.w(TAG, "allocateAshmemBlocks failed", exception);
            }
        }
        return created;
    }

    public long allocateNativeBlocks(int count, int eachMb) {
        return NativeBridge.allocateNativeBlocks(count, eachMb);
    }

    public int spawnExtraThreads(int count) {
        threadStop.set(false);
        for (int i = 0; i < count; i++) {
            Thread thread = new Thread(() -> {
                byte[] stackLocal = new byte[64 * 1024];
                while (!threadStop.get()) {
                    stackLocal[0] = (byte) (stackLocal[0] + 1);
                    try {
                        Thread.sleep(1000);
                    } catch (InterruptedException interruptedException) {
                        Thread.currentThread().interrupt();
                        return;
                    }
                }
            }, "memory-lab-thread-" + i);
            thread.start();
            LeakySingletons.EXTRA_THREADS.add(thread);
        }
        return LeakySingletons.EXTRA_THREADS.size();
    }

    public int createLeakyWebViews(Activity activity, int count) {
        for (int i = 0; i < count; i++) {
            WebView webView = new WebView(activity);
            String html = "<html><body><h2>memory-lab" + i + "</h2>"
                    + "<canvas id='c' width='1920' height='1080'></canvas>"
                    + "<script>var x=document.getElementById('c').getContext('2d');"
                    + "for(var j=0;j<2000;j++){x.fillStyle='rgb('+(j%255)+',80,120)';"
                    + "x.fillRect((j*7)%1800,(j*13)%1000,120,80);}</script>"
                    + "</body></html>";
            webView.loadDataWithBaseURL("https://memory.lab/", html, "text/html", "UTF-8", null);
            LeakySingletons.WEBVIEW_LEAKS.add(webView);
        }
        return LeakySingletons.WEBVIEW_LEAKS.size();
    }

    public void startJankStorm(int frameCount, int blockMs) {
        stopJankStorm();
        final int[] remaining = {Math.max(frameCount, 1)};
        final int blockDuration = Math.max(blockMs, 1);
        jankRunnable = new Runnable() {
            @Override
            public void run() {
                if (remaining[0] <= 0) {
                    jankRunnable = null;
                    return;
                }

                remaining[0] = remaining[0] - 1;
                long end = SystemClock.uptimeMillis() + blockDuration;
                while (SystemClock.uptimeMillis() < end) {
                    jankSink = jankSink + Math.sqrt((jankSink % 1000.0) + remaining[0] + 1.0);
                }

                if (remaining[0] > 0) {
                    mainHandler.postDelayed(this, 4);
                } else {
                    jankRunnable = null;
                }
            }
        };
        mainHandler.post(jankRunnable);
    }

    public void stopJankStorm() {
        Runnable runnable = jankRunnable;
        if (runnable != null) {
            mainHandler.removeCallbacks(runnable);
            jankRunnable = null;
        }
    }

    public String dumpHprof(Activity activity) {
        File outputDir = activity.getExternalFilesDir("hprof");
        if (outputDir == null) {
            outputDir = activity.getFilesDir();
        }
        String name = String.format(Locale.US, "memory-lab-%d.hprof", System.currentTimeMillis());
        File output = new File(outputDir, name);
        try {
            Debug.dumpHprofData(output.getAbsolutePath());
            return output.getAbsolutePath();
        } catch (IOException exception) {
            return "dump failed: " + exception.getMessage();
        }
    }

    public void clearJavaSide() {
        stopJankStorm();
        LeakySingletons.JAVA_LEAK_BUCKET.clear();
        LeakySingletons.LOW_UTIL_COLLECTIONS.clear();
        LeakySingletons.VIEW_STORM.clear();
        LeakySingletons.FRAGMENT_LEAKS.clear();
        LeakySingletons.SERVICE_LEAKS.clear();
        LeakySingletons.RECEIVER_LEAKS.clear();
        LeakySingletons.BUSINESS_LRU_CACHES.clear();
        for (Bitmap bitmap : LeakySingletons.BITMAP_CACHE) {
            if (bitmap != null && !bitmap.isRecycled()) {
                bitmap.recycle();
            }
        }
        LeakySingletons.BITMAP_CACHE.clear();
        LeakySingletons.DIRECT_BUFFERS.clear();
        for (WebView webView : LeakySingletons.WEBVIEW_LEAKS) {
            webView.stopLoading();
            webView.loadUrl("about:blank");
            webView.destroy();
        }
        LeakySingletons.WEBVIEW_LEAKS.clear();
        LeakySingletons.leakedActivity = null;
    }

    public long clearNativeSide() {
        for (SharedMemory sharedMemory : LeakySingletons.ASHMEM_BUFFERS) {
            try {
                sharedMemory.close();
            } catch (RuntimeException exception) {
                Log.w(TAG, "clearNativeSide failed", exception);
            }
        }
        LeakySingletons.ASHMEM_BUFFERS.clear();
        return NativeBridge.freeAllNativeBlocks();
    }

    public int stopThreads() {
        threadStop.set(true);
        for (Thread thread : LeakySingletons.EXTRA_THREADS) {
            thread.interrupt();
        }
        int count = LeakySingletons.EXTRA_THREADS.size();
        LeakySingletons.EXTRA_THREADS.clear();
        return count;
    }

    public void clearAll() {
        clearJavaSide();
        clearNativeSide();
        stopThreads();
        stopJankStorm();
        System.gc();
    }

    public String snapshot() {
        Runtime runtime = Runtime.getRuntime();
        long maxMb = runtime.maxMemory() / (1024 * 1024);
        long totalMb = runtime.totalMemory() / (1024 * 1024);
        long freeMb = runtime.freeMemory() / (1024 * 1024);
        long usedMb = totalMb - freeMb;
        int pid = Process.myPid();
        return "pid=" + pid
                + "\njavaUsedMb=" + usedMb + "/" + maxMb
                + "\njavaLeakObjects=" + LeakySingletons.JAVA_LEAK_BUCKET.size()
                + "\nbitmapCount=" + LeakySingletons.BITMAP_CACHE.size()
                + "\ndirectBuffers=" + LeakySingletons.DIRECT_BUFFERS.size()
                + "\nashmemBlocks=" + LeakySingletons.ASHMEM_BUFFERS.size()
                + "\nthreads=" + LeakySingletons.EXTRA_THREADS.size()
                + "\nwebViews=" + LeakySingletons.WEBVIEW_LEAKS.size()
                + "\nviewStorm=" + LeakySingletons.VIEW_STORM.size()
                + "\nfragments=" + LeakySingletons.FRAGMENT_LEAKS.size()
                + "\nservices=" + LeakySingletons.SERVICE_LEAKS.size()
                + "\nreceivers=" + LeakySingletons.RECEIVER_LEAKS.size()
                + "\nbusinessLruCaches=" + LeakySingletons.BUSINESS_LRU_CACHES.size()
                + "\njankStormRunning=" + (jankRunnable != null)
                + "\n" + NativeBridge.getNativeStats();
    }

}
