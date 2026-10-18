cmake_minimum_required(VERSION 3.20)

# Build: see build.ps1 (it supplies the llvm-mingw i686 toolchain from Tools).
project(wiz8ws C CXX)

if(NOT CMAKE_SIZEOF_VOID_P EQUAL 4)
    message(FATAL_ERROR "A 32-bit (x86) build is required: Wiz8.exe is a 32-bit process.")
endif()

# The patch version: the single line of VERSION (also used by the installer and the package).
file(STRINGS "${CMAKE_SOURCE_DIR}/VERSION" WIZ8WS_VERSION LIMIT_COUNT 1)
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${CMAKE_SOURCE_DIR}/VERSION")

# MinHook — hooking library (submodule third_party/minhook).
add_library(minhook STATIC
    third_party/minhook/src/buffer.c
    third_party/minhook/src/hook.c
    third_party/minhook/src/trampoline.c
    third_party/minhook/src/hde/hde32.c
)
target_include_directories(minhook PUBLIC third_party/minhook/include)

# Our DLL. The file name is version.dll: the game's sr.dll loads it under that name.
add_library(wiz8ws SHARED
    src/dllmain.cpp
    src/proxy_version.cpp
    src/hooks_window.cpp
    src/log.cpp
    src/config.cpp
    src/exe_version.cpp
    src/patch.cpp
    src/layout.cpp
    src/signature.cpp
    src/hooks_video.cpp
    src/hooks_mouse.cpp
    src/hooks_input.cpp
    src/sr_api.cpp
    src/hooks_hud.cpp
    src/hooks_view3d.cpp
    src/hooks_diff.cpp
    src/hooks_hybrid.cpp
    src/version.def
)
set_target_properties(wiz8ws PROPERTIES OUTPUT_NAME "version" PREFIX "")
target_compile_features(wiz8ws PRIVATE cxx_std_17)
target_compile_definitions(wiz8ws PRIVATE WIZ8WS_VERSION="${WIZ8WS_VERSION}" WIN32_LEAN_AND_MEAN NOMINMAX)
target_compile_options(wiz8ws PRIVATE -Wall -Wextra -Wno-unused-parameter)
target_link_libraries(wiz8ws PRIVATE minhook bcrypt)
# Static linking of the C++ runtime: the DLL does not drag in libc++.dll etc.
target_link_options(wiz8ws PRIVATE -static -static-libgcc -s)
