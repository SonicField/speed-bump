/*
 * ThreadSanitizer test for speed-bump core functions.
 *
 * Build: gcc -fsanitize=thread -O2 -pthread -o tsan_test tests/tsan_test.c
 * Run: ./tsan_test
 *
 * This tests the core spin_delay logic without Python dependencies.
 */

#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>
#include <stdbool.h>

/* Architecture-specific pause instruction */
#ifdef __x86_64__
#include <immintrin.h>
#define CPU_PAUSE() _mm_pause()
#elif defined(__aarch64__)
#define CPU_PAUSE() __asm__ __volatile__("yield")
#else
#define CPU_PAUSE() ((void)0)
#endif

/* ============================================================================
 * Core functions (copied from _core.c for standalone testing)
 * ============================================================================ */

static uint64_t g_clock_overhead_ns = 0;
static bool g_calibrated = false;

static inline uint64_t timespec_to_ns(const struct timespec *ts) {
    return (uint64_t)ts->tv_sec * 1000000000ULL + (uint64_t)ts->tv_nsec;
}

static void calibrate_clock(void) {
    struct timespec ts, start, end;
    const int WARMUP = 1000;
    const int ITERS = 10000;  /* Reduced for test speed */

    for (int i = 0; i < WARMUP; i++) {
        clock_gettime(CLOCK_MONOTONIC, &ts);
    }

    clock_gettime(CLOCK_MONOTONIC, &start);
    for (int i = 0; i < ITERS; i++) {
        clock_gettime(CLOCK_MONOTONIC, &ts);
    }
    clock_gettime(CLOCK_MONOTONIC, &end);

    uint64_t elapsed = timespec_to_ns(&end) - timespec_to_ns(&start);
    g_clock_overhead_ns = elapsed / ITERS;
    g_calibrated = true;
}

static void spin_delay_ns(uint64_t delay_ns) {
    struct timespec start, now;

    clock_gettime(CLOCK_MONOTONIC, &start);
    uint64_t end_ns = timespec_to_ns(&start) + delay_ns;

    for (;;) {
        clock_gettime(CLOCK_MONOTONIC, &now);
        if (timespec_to_ns(&now) >= end_ns) {
            break;
        }
        CPU_PAUSE();
    }
}

/* ============================================================================
 * Test harness
 * ============================================================================ */

#define N_THREADS 8
#define N_ITERATIONS 100
#define DELAY_NS 10000  /* 10μs */

typedef struct {
    int thread_id;
    uint64_t total_delay;
} thread_result_t;

static pthread_barrier_t start_barrier;
static thread_result_t results[N_THREADS];

static void* worker(void* arg) {
    int id = *(int*)arg;

    /* Wait for all threads to be ready */
    pthread_barrier_wait(&start_barrier);

    struct timespec t0, t1;
    clock_gettime(CLOCK_MONOTONIC, &t0);

    for (int i = 0; i < N_ITERATIONS; i++) {
        spin_delay_ns(DELAY_NS);
    }

    clock_gettime(CLOCK_MONOTONIC, &t1);
    results[id].thread_id = id;
    results[id].total_delay = timespec_to_ns(&t1) - timespec_to_ns(&t0);

    return NULL;
}

int main(void) {
    printf("ThreadSanitizer test for speed-bump\n");
    printf("===================================\n");
    printf("Threads: %d, Iterations: %d, Delay: %d ns\n\n",
           N_THREADS, N_ITERATIONS, DELAY_NS);

    /* Calibrate first (single-threaded) */
    printf("Calibrating... ");
    calibrate_clock();
    printf("overhead: %lu ns\n\n", (unsigned long)g_clock_overhead_ns);

    /* Initialize barrier */
    pthread_barrier_init(&start_barrier, NULL, N_THREADS);

    /* Create thread IDs */
    int thread_ids[N_THREADS];
    for (int i = 0; i < N_THREADS; i++) {
        thread_ids[i] = i;
    }

    /* Launch threads */
    pthread_t threads[N_THREADS];
    printf("Launching %d threads...\n", N_THREADS);

    for (int i = 0; i < N_THREADS; i++) {
        if (pthread_create(&threads[i], NULL, worker, &thread_ids[i]) != 0) {
            perror("pthread_create");
            return 1;
        }
    }

    /* Wait for completion */
    for (int i = 0; i < N_THREADS; i++) {
        pthread_join(threads[i], NULL);
    }

    /* Report results */
    printf("\nResults:\n");
    uint64_t expected_min = (uint64_t)N_ITERATIONS * DELAY_NS;
    for (int i = 0; i < N_THREADS; i++) {
        double ratio = (double)results[i].total_delay / expected_min;
        printf("  Thread %d: %lu ns (%.2fx expected)\n",
               results[i].thread_id,
               (unsigned long)results[i].total_delay,
               ratio);
    }

    pthread_barrier_destroy(&start_barrier);

    printf("\nTest complete. If no ThreadSanitizer warnings above, "
           "spin_delay_ns is race-free.\n");

    return 0;
}
