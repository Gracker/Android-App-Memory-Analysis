# HPROF Parser Enhancement TODO

## Overview
Enhance the HPROF parser to provide deeper memory analysis capabilities including GC Root analysis, reference graph, dominator tree, retained size calculation, and memory leak detection.

**Status: COMPLETED**

---

## Phase 1: Enhanced Data Collection

### 1.1 Parse GC Root Records
- [x] Parse ROOT_UNKNOWN (0xFF)
- [x] Parse ROOT_JNI_GLOBAL (0x01)
- [x] Parse ROOT_JNI_LOCAL (0x02)
- [x] Parse ROOT_JAVA_FRAME (0x03)
- [x] Parse ROOT_NATIVE_STACK (0x04)
- [x] Parse ROOT_STICKY_CLASS (0x05)
- [x] Parse ROOT_THREAD_BLOCK (0x06)
- [x] Parse ROOT_MONITOR_USED (0x07)
- [x] Parse ROOT_THREAD_OBJ (0x08)
- [x] Store GC roots with type information

### 1.2 Store Class Field Definitions
- [x] Parse instance field definitions (name, type)
- [x] Build class hierarchy (super class chain)
- [x] Store field offsets for each class

### 1.3 Parse Instance Field Values
- [x] Read field values instead of skipping
- [x] Extract object references from fields
- [x] Store instance data for later analysis

### 1.4 Parse Object Array Elements
- [x] Read array element references
- [x] Store array content for reference graph

---

## Phase 2: Build Reference Graph

### 2.1 Build Outgoing Reference Graph
- [x] Create object -> referenced objects mapping
- [x] Include instance field references
- [x] Include array element references

### 2.2 Build Incoming Reference Graph
- [x] Create object -> referencing objects mapping
- [x] Enable reverse traversal

### 2.3 Implement Path to GC Root Query
- [x] BFS/DFS from object to GC Root
- [x] Find shortest path
- [x] Support excluding weak/soft references

---

## Phase 3: Dominator Tree & Retained Size

### 3.1 Reachability Analysis from GC Roots
- [x] Mark all reachable objects from GC Roots
- [x] Identify unreachable objects (garbage)

### 3.2 Implement Dominator Tree Algorithm
- [x] Implement simplified dominator algorithm
- [x] Build dominator tree structure
- [x] Handle cycles in reference graph

### 3.3 Calculate Retained Size
- [x] Compute retained set for each object
- [x] Sum shallow sizes for retained size
- [x] Support top-N retained size query

---

## Phase 4: Memory Leak Detection

### 4.1 Detect Duplicate Instances
- [x] Detect multiple Activity instances
- [x] Detect multiple Fragment instances
- [x] Flag potential leaks

### 4.2 Detect Accumulation Points
- [x] Find objects with large retained/shallow ratio
- [x] Identify memory accumulation patterns

### 4.3 Generate Leak Suspects Report
- [x] Summarize top leak suspects
- [x] Show path to GC Root for each suspect
- [x] Provide recommendations

---

## Phase 5: Advanced Analysis

### 5.1 String Content Analysis
- [x] Read String.value (char[]) content
- [x] Detect duplicate strings
- [x] Calculate wasted memory from duplicates

### 5.2 Bitmap Size Analysis
- [x] Identify android.graphics.Bitmap instances
- [x] Calculate actual bitmap memory (width * height * bytes per pixel)
- [x] List large bitmaps

### 5.3 Collection Class Analysis
- [x] Analyze HashMap capacity vs size
- [x] Analyze ArrayList capacity vs size
- [x] Detect over-allocated collections

### 5.4 Update Output Report Format
- [x] Add GC Root statistics section
- [x] Add Dominator Tree section
- [x] Add Leak Suspects section
- [x] Add String analysis section
- [x] Add Bitmap analysis section

---

## Progress Tracking

| Phase | Task | Status | Date |
|-------|------|--------|------|
| 1.1 | Parse GC Root Records | Completed | 2024-12-24 |
| 1.2 | Store Class Field Definitions | Completed | 2024-12-24 |
| 1.3 | Parse Instance Field Values | Completed | 2024-12-24 |
| 1.4 | Parse Object Array Elements | Completed | 2024-12-24 |
| 2.1 | Build Outgoing Reference Graph | Completed | 2024-12-24 |
| 2.2 | Build Incoming Reference Graph | Completed | 2024-12-24 |
| 2.3 | Implement Path to GC Root | Completed | 2024-12-24 |
| 3.1 | Reachability Analysis | Completed | 2024-12-24 |
| 3.2 | Dominator Tree Algorithm | Completed | 2024-12-24 |
| 3.3 | Calculate Retained Size | Completed | 2024-12-24 |
| 4.1 | Detect Duplicate Instances | Completed | 2024-12-24 |
| 4.2 | Detect Accumulation Points | Completed | 2024-12-24 |
| 4.3 | Generate Leak Suspects Report | Completed | 2024-12-24 |
| 5.1 | String Content Analysis | Completed | 2024-12-24 |
| 5.2 | Bitmap Size Analysis | Completed | 2024-12-24 |
| 5.3 | Collection Class Analysis | Completed | 2024-12-24 |
| 5.4 | Update Output Report Format | Completed | 2024-12-24 |

---

## New Features Summary

The enhanced HPROF parser now provides:

1. **GC Root Analysis**: Parses and categorizes all 16 types of GC roots
2. **Reference Graph**: Builds bidirectional object reference graph
3. **Dominator Tree**: Computes dominator relationships between objects
4. **Retained Size**: Calculates how much memory each object retains
5. **Leak Detection**: Identifies potential memory leaks (duplicate instances, accumulation points)
6. **String Analysis**: Detects duplicate strings and calculates wasted memory
7. **Bitmap Analysis**: Analyzes Bitmap dimensions and estimated memory
8. **Collection Analysis**: Detects over-allocated collections

## Usage

```bash
# Full deep analysis (default)
python3 tools/hprof_parser.py -f <hprof_file>

# Quick analysis without deep features
python3 tools/hprof_parser.py -f <hprof_file> --no-deep

# Customize output
python3 tools/hprof_parser.py -f <hprof_file> -t 30 -m 0.5 -o output.txt
```

---

## References
- [HPROF Format Specification](https://www.cs.rice.edu/~la5/doc/hprof.html/d1/d3f/hprof__b__spec_8h_source.html)
- [Eclipse MAT Dominator Tree](https://help.eclipse.org/latest/topic/org.eclipse.mat.ui.help/concepts/dominatortree.html)
- [HeapHero Dominator Tree Guide](https://blog.heaphero.io/dominator-tree-how-to-use-them-in-memory-analysis/)
- [GitHub hprof-parser](https://github.com/eaftan/hprof-parser)
