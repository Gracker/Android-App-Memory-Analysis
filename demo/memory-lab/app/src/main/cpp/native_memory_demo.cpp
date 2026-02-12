#include <jni.h>
#include <string>
#include <vector>
#include <cstring>
#include <sys/mman.h>
#include <unistd.h>

namespace {

struct NativeBlock {
    void* ptr;
    size_t size;
    bool use_mmap;
};

std::vector<NativeBlock> g_blocks;

size_t total_allocated_bytes() {
    size_t total = 0;
    for (const auto& block : g_blocks) {
        total += block.size;
    }
    return total;
}

void free_block(const NativeBlock& block) {
    if (block.ptr == nullptr || block.size == 0) {
        return;
    }
    if (block.use_mmap) {
        munmap(block.ptr, block.size);
    } else {
        free(block.ptr);
    }
}

}

extern "C" JNIEXPORT jlong JNICALL
Java_com_androidperformance_memorylab_NativeBridge_allocateNativeBlocks(
        JNIEnv* env, jclass, jint block_count, jint block_size_mb) {
    if (block_count <= 0 || block_size_mb <= 0) {
        return static_cast<jlong>(total_allocated_bytes());
    }

    const size_t block_size = static_cast<size_t>(block_size_mb) * 1024 * 1024;
    for (int i = 0; i < block_count; ++i) {
        bool use_mmap = (i % 2 == 0);
        void* ptr = nullptr;

        if (use_mmap) {
            ptr = mmap(nullptr, block_size, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
            if (ptr == MAP_FAILED) {
                ptr = nullptr;
            }
        } else {
            ptr = malloc(block_size);
        }

        if (ptr == nullptr) {
            continue;
        }

        memset(ptr, 0x5A, block_size);
        g_blocks.push_back(NativeBlock{ptr, block_size, use_mmap});
    }

    return static_cast<jlong>(total_allocated_bytes());
}

extern "C" JNIEXPORT jlong JNICALL
Java_com_androidperformance_memorylab_NativeBridge_freeAllNativeBlocks(
        JNIEnv*, jclass) {
    size_t before = total_allocated_bytes();
    for (const auto& block : g_blocks) {
        free_block(block);
    }
    g_blocks.clear();
    return static_cast<jlong>(before);
}

extern "C" JNIEXPORT jstring JNICALL
Java_com_androidperformance_memorylab_NativeBridge_getNativeStats(
        JNIEnv* env, jclass) {
    const size_t bytes = total_allocated_bytes();
    const double mb = static_cast<double>(bytes) / (1024.0 * 1024.0);

    std::string out = "nativeBlocks=" + std::to_string(g_blocks.size())
            + "\nnativeBytes=" + std::to_string(bytes)
            + "\nnativeMb=" + std::to_string(mb);
    return env->NewStringUTF(out.c_str());
}
