#!/bin/bash
# Run C-level tests for speed-bump
#
# Usage:
#   ./tests/run_c_tests.sh          # Run all C tests
#   ./tests/run_c_tests.sh tsan     # Run ThreadSanitizer test only
#   ./tests/run_c_tests.sh asan     # Run AddressSanitizer test only
#
# Requirements:
#   - clang (for sanitizer support)
#   - pthread
#
# What this tests:
#   - tsan: Verifies spin_delay_ns is race-free under concurrent execution
#   - asan: Verifies no memory errors in spin_delay_ns (future)
#
# These tests exercise the core C code independently of Python, which:
#   1. Avoids false positives from uninstrumented Python runtime
#   2. Tests the actual functions that run in parallel on FTP
#   3. Provides faster feedback than full Python integration tests

set -e

cd "$(dirname "$0")/.."

TESTS_DIR="tests"
BUILD_DIR="tests/build"

mkdir -p "$BUILD_DIR"

run_tsan() {
    echo "=== ThreadSanitizer Test ==="
    echo ""

    # Check for clang
    if ! command -v clang &> /dev/null; then
        echo "ERROR: clang not found. Install clang for sanitizer support."
        exit 1
    fi

    echo "Building with -fsanitize=thread..."
    clang -fsanitize=thread -O2 -pthread \
        -o "$BUILD_DIR/tsan_test" \
        "$TESTS_DIR/tsan_test.c"

    echo "Running tsan test (8 threads, 100 iterations each)..."
    echo ""

    if "$BUILD_DIR/tsan_test" 2>&1; then
        echo ""
        echo "PASS: No ThreadSanitizer warnings detected"
        return 0
    else
        echo ""
        echo "FAIL: ThreadSanitizer detected issues"
        return 1
    fi
}

run_asan() {
    echo "=== AddressSanitizer Test ==="
    echo ""

    if ! command -v clang &> /dev/null; then
        echo "ERROR: clang not found. Install clang for sanitizer support."
        exit 1
    fi

    echo "Building with -fsanitize=address..."
    clang -fsanitize=address -O2 -pthread \
        -o "$BUILD_DIR/asan_test" \
        "$TESTS_DIR/tsan_test.c"

    echo "Running asan test..."
    echo ""

    if "$BUILD_DIR/asan_test" 2>&1; then
        echo ""
        echo "PASS: No AddressSanitizer warnings detected"
        return 0
    else
        echo ""
        echo "FAIL: AddressSanitizer detected issues"
        return 1
    fi
}

run_all() {
    local failed=0

    run_tsan || failed=1
    echo ""
    run_asan || failed=1

    echo ""
    echo "=== Summary ==="
    if [ $failed -eq 0 ]; then
        echo "All C tests passed"
    else
        echo "Some C tests failed"
    fi

    return $failed
}

# Clean up build artifacts
cleanup() {
    rm -rf "$BUILD_DIR"
}

# Parse arguments
case "${1:-all}" in
    tsan)
        run_tsan
        ;;
    asan)
        run_asan
        ;;
    all)
        run_all
        ;;
    clean)
        cleanup
        echo "Cleaned build directory"
        ;;
    *)
        echo "Usage: $0 [tsan|asan|all|clean]"
        exit 1
        ;;
esac
