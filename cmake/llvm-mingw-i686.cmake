# Toolchain: 32-bit Windows (x86) via the portable llvm-mingw from Tools.
set(CMAKE_SYSTEM_NAME Windows)
set(CMAKE_SYSTEM_PROCESSOR i686)

get_filename_component(_root "${CMAKE_CURRENT_LIST_DIR}/.." ABSOLUTE)
set(_bin "${_root}/Tools/llvm-mingw/bin")

set(CMAKE_C_COMPILER   "${_bin}/i686-w64-mingw32-clang.exe")
set(CMAKE_CXX_COMPILER "${_bin}/i686-w64-mingw32-clang++.exe")
set(CMAKE_RC_COMPILER  "${_bin}/i686-w64-mingw32-windres.exe")
