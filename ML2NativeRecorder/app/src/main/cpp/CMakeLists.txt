cmake_minimum_required(VERSION 3.22.1)
project(native-lib)

add_library(
        native-lib
        SHARED
        native-lib.cpp
)

# ✅ Magic Leap C SDK root (your real path)
set(MLSDK_ROOT "/Users/azyl/MagicLeap/mlsdk/v1.12.0")

# ✅ Headers
target_include_directories(native-lib PRIVATE
        ${MLSDK_ROOT}/include
)

# ✅ Import ML perception shared library (path may vary; see step 2 below)
add_library(perception_magicleap SHARED IMPORTED)
set_target_properties(perception_magicleap PROPERTIES
        IMPORTED_LOCATION ${MLSDK_ROOT}/lib/ml2/libperception.magicleap.so
)

find_library(log-lib log)

target_link_libraries(
        native-lib
        perception_magicleap
        ${log-lib}
)
