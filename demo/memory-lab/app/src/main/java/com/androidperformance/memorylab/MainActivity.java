package com.androidperformance.memorylab;

import android.os.Bundle;
import android.widget.Button;
import android.widget.TextView;
import android.widget.Toast;

import androidx.annotation.Nullable;
import androidx.appcompat.app.AppCompatActivity;

public class MainActivity extends AppCompatActivity {

    private final MemoryScenarioController controller = new MemoryScenarioController();
    private TextView tvStatus;
    private volatile boolean oneClickRunning;

    @Override
    protected void onCreate(@Nullable Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        tvStatus = findViewById(R.id.tvStatus);
        setupActions();
        updateStatus("ready");
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        updateStatus("activity destroyed");
    }

    private void setupActions() {
        bind(R.id.btnRunAll, this::runAllScenariosOneClick);

        bind(R.id.btnJavaLeak, () -> {
            controller.leakActivity(this);
            int chunks = controller.allocateJavaLeakObjects(96);
            int collections = controller.inflateLowUtilizationCollections();
            updateStatus("java leak chunks=" + chunks + ", collections=" + collections);
        });

        bind(R.id.btnBitmaps, () -> {
            int count = controller.allocateBitmapDuplicates();
            updateStatus("bitmap cache=" + count);
        });

        bind(R.id.btnDirectBuffer, () -> {
            int count = controller.allocateDirectBuffers(80, 512);
            updateStatus("direct buffers=" + count);
        });

        bind(R.id.btnNativeMalloc, () -> {
            long bytes = controller.allocateNativeBlocks(30, 4);
            updateStatus("native allocated bytes=" + bytes);
        });

        bind(R.id.btnAshmem, () -> {
            int count = controller.allocateAshmemBlocks(18, 4);
            updateStatus("ashmem blocks added=" + count);
        });

        bind(R.id.btnThreads, () -> {
            int count = controller.spawnExtraThreads(40);
            updateStatus("extra threads=" + count);
        });

        bind(R.id.btnWebView, () -> {
            int count = controller.createLeakyWebViews(this, 4);
            updateStatus("webviews=" + count);
        });

        bind(R.id.btnDumpHprof, () -> {
            String output = controller.dumpHprof(this);
            Toast.makeText(this, output, Toast.LENGTH_LONG).show();
            updateStatus("hprof=" + output);
        });

        bind(R.id.btnClearJava, () -> {
            controller.clearJavaSide();
            updateStatus("cleared java side");
        });

        bind(R.id.btnClearNative, () -> {
            long bytes = controller.clearNativeSide();
            updateStatus("freed native bytes=" + bytes);
        });

        bind(R.id.btnClearThreads, () -> {
            int count = controller.stopThreads();
            updateStatus("stopped threads=" + count);
        });

        bind(R.id.btnClearAll, () -> {
            controller.clearAll();
            updateStatus("cleared all scenarios");
        });
    }

    private void runAllScenariosOneClick() {
        if (oneClickRunning) {
            Toast.makeText(this, "One-click scenario is already running", Toast.LENGTH_SHORT).show();
            return;
        }

        oneClickRunning = true;
        updateStatus("one-click: running...");

        Thread worker = new Thread(() -> {
            try {
                controller.leakActivity(this);
                int javaChunks = controller.allocateJavaLeakObjects(96);
                int collections = controller.inflateLowUtilizationCollections();
                int fragments = controller.createLeakyFragments(24, 512);
                int services = controller.createLeakyServices(16, 512);
                int receivers = controller.createLeakyReceivers(24, 256);
                int lruCaches = controller.createMisconfiguredLruCaches(2);
                int bitmaps = controller.allocateBitmapDuplicates();
                int directBuffers = controller.allocateDirectBuffers(80, 512);
                long nativeBytes = controller.allocateNativeBlocks(30, 4);
                int ashmem = controller.allocateAshmemBlocks(18, 4);
                int threads = controller.spawnExtraThreads(40);

                runOnUiThread(() -> {
                    int views = controller.inflateViewStorm(this, 750);
                    int webviews = controller.createLeakyWebViews(this, 4);
                    controller.startJankStorm(260, 24);
                    oneClickRunning = false;
                    updateStatus(
                            "one-click done"
                                    + "\njavaChunks=" + javaChunks
                                    + "\ncollections=" + collections
                                    + "\nfragments=" + fragments
                                    + "\nservices=" + services
                                    + "\nreceivers=" + receivers
                                    + "\nlruCaches=" + lruCaches
                                    + "\nbitmaps=" + bitmaps
                                    + "\ndirectBuffers=" + directBuffers
                                    + "\nnativeBytes=" + nativeBytes
                                    + "\nashmem=" + ashmem
                                    + "\nthreads=" + threads
                                    + "\nviews=" + views
                                    + "\nwebviews=" + webviews);
                });
            } catch (RuntimeException exception) {
                runOnUiThread(() -> {
                    oneClickRunning = false;
                    Toast.makeText(this, "one-click failed: " + exception.getMessage(), Toast.LENGTH_LONG).show();
                    updateStatus("one-click failed");
                });
            }
        }, "memory-lab-one-click");

        worker.start();
    }

    private void bind(int id, Runnable runnable) {
        Button button = findViewById(id);
        button.setOnClickListener(v -> runnable.run());
    }

    private void updateStatus(String headline) {
        String snapshot = controller.snapshot();
        tvStatus.setText(headline + "\n\n" + snapshot);
    }
}
