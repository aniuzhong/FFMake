# equivalence: ffmpeg-20260905-mingw-x86_64-llvm vs original ffmpeg-20260901-mingw-x86_64-llvm

verdict: PASS (hard gates failed: 0)

- [PASS] configure flags (manifest, prefix-normalized)
- [PASS] new binary runs; version = ffmpeg version git-2026-09-01-9029d64 Copyright (c) 2000-2026 th
- [PASS] version banner
- [PASS] runtime configuration line
- [PASS] libav* headers (145 files byte-equal)
- [PASS] product exported symbols (0 libs)
- [PASS] product executables present -- []
- [INFO] reference binary runs on this host: True
- [INFO] reference glibc/libstdc++ requirement: {}
- [INFO] rebuilt glibc/libstdc++ requirement: {}
- [INFO] system soname closure: old-only [] / new-only []
- [INFO] bin/ extras beyond product: old-only ['davs2', 'flite', 'flite_cmu_time_awb', 'flite_cmu_us_awb', 'flite_cmu_us_kal', 'flite_cmu_us_kal16', 'flite_cmu_us_rms', 'flite_cmu_us_slt'] / new-only ['SPIRV.dll', 'cache.json', 'glslang.dll', 'glslang.exe', 'glslangValidator.exe', 'glslc.exe', 'libLerc.dll', 'libSPIRV-Tools-diff.dll']
- [INFO] sysroot-history headers not in clean build (0): []
