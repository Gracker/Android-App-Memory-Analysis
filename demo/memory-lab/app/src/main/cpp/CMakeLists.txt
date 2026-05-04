cmake_minimum_required(VERSION 3.22.1)

project(memorylab)

add_library(
        memorylab
        SHARED
        native_memory_demo.cpp)

find_library(
        log-lib
        log)

target_link_libraries(
        memorylab
        ${log-lib})

target_link_options(
        memorylab
        PRIVATE
        "-Wl,-z,max-page-size=16384"
        "-Wl,-z,common-page-size=16384")
