package com.androidperformance.memorylab;

public final class NativeBridge {
    static {
        System.loadLibrary("memorylab");
    }

    private NativeBridge() {
    }

    public static native long allocateNativeBlocks(int blockCount, int blockSizeMb);

    public static native long freeAllNativeBlocks();

    public static native String getNativeStats();
}
