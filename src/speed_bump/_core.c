/*
 * Speed Bump - Core C Extension
 *
 * Provides:
 * - Clock calibration for measuring clock_gettime overhead
 * - Spin delay implementation
 * - PEP 669 monitoring integration (future phases)
 */

#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <time.h>
#include <stdint.h>
#include <stdio.h>
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
 * Module State
 *
 * Thread-safety notes:
 * - g_clock_overhead_ns and g_calibrated are written once during module init
 * - Python's import machinery serialises module init (even on FTP)
 * - After init, these are read-only and safe to access from any thread
 * - spin_delay_ns() uses only local variables and is fully thread-safe
 *
 * Verified with ThreadSanitizer: spin_delay_ns shows no races when called
 * from 8 concurrent threads. calibrate_clock would race if called
 * concurrently, but this never happens due to import serialisation.
 * ============================================================================ */

static uint64_t g_clock_overhead_ns = 0;
static bool g_calibrated = false;

/* ============================================================================
 * Time Utilities
 * ============================================================================ */

static inline uint64_t timespec_to_ns(const struct timespec *ts) {
    return (uint64_t)ts->tv_sec * 1000000000ULL + (uint64_t)ts->tv_nsec;
}

/* ============================================================================
 * Calibration
 * ============================================================================ */

static void calibrate_clock(void) {
    struct timespec ts, start, end;
    const int WARMUP = 1000;
    const int ITERS = 100000;

    /* Warmup - prime caches and TLB */
    for (int i = 0; i < WARMUP; i++) {
        clock_gettime(CLOCK_MONOTONIC, &ts);
    }

    /* Measure */
    clock_gettime(CLOCK_MONOTONIC, &start);
    for (int i = 0; i < ITERS; i++) {
        clock_gettime(CLOCK_MONOTONIC, &ts);
    }
    clock_gettime(CLOCK_MONOTONIC, &end);

    uint64_t elapsed = timespec_to_ns(&end) - timespec_to_ns(&start);
    g_clock_overhead_ns = elapsed / ITERS;
    g_calibrated = true;

    fprintf(stderr, "speed_bump: clock_gettime overhead: %lu ns\n",
            (unsigned long)g_clock_overhead_ns);
    fprintf(stderr, "speed_bump: minimum achievable delay: %lu ns\n",
            (unsigned long)(2 * g_clock_overhead_ns));
}

/* ============================================================================
 * Spin Delay
 * ============================================================================ */

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
 * Python API
 * ============================================================================ */

PyDoc_STRVAR(py_spin_delay_ns_doc,
"spin_delay_ns(nanoseconds)\n"
"\n"
"Spin-wait for the specified number of nanoseconds.\n"
"\n"
"This function does NOT yield the thread; it busy-waits using\n"
"clock_gettime(CLOCK_MONOTONIC) to measure elapsed time.\n"
"\n"
"Args:\n"
"    nanoseconds: Number of nanoseconds to delay (uint64).\n"
);

static PyObject* py_spin_delay_ns(PyObject* self, PyObject* args) {
    (void)self;
    unsigned long long delay;

    if (!PyArg_ParseTuple(args, "K", &delay)) {
        return NULL;
    }

    spin_delay_ns((uint64_t)delay);
    Py_RETURN_NONE;
}

PyDoc_STRVAR(py_get_clock_overhead_ns_doc,
"get_clock_overhead_ns()\n"
"\n"
"Get the calibrated clock_gettime overhead in nanoseconds.\n"
"\n"
"Returns:\n"
"    int: The measured overhead per clock_gettime call.\n"
);

static PyObject* py_get_clock_overhead_ns(PyObject* self, PyObject* args) {
    (void)self;
    (void)args;
    return PyLong_FromUnsignedLongLong(g_clock_overhead_ns);
}

PyDoc_STRVAR(py_get_min_delay_ns_doc,
"get_min_delay_ns()\n"
"\n"
"Get the minimum achievable delay in nanoseconds.\n"
"\n"
"This is 2x the clock_gettime overhead, since spin_delay_ns\n"
"requires at least two clock reads (start and end).\n"
"\n"
"Returns:\n"
"    int: The minimum achievable delay.\n"
);

static PyObject* py_get_min_delay_ns(PyObject* self, PyObject* args) {
    (void)self;
    (void)args;
    return PyLong_FromUnsignedLongLong(2 * g_clock_overhead_ns);
}

PyDoc_STRVAR(py_is_calibrated_doc,
"is_calibrated()\n"
"\n"
"Check if the clock has been calibrated.\n"
"\n"
"Returns:\n"
"    bool: True if calibration has completed.\n"
);

static PyObject* py_is_calibrated(PyObject* self, PyObject* args) {
    (void)self;
    (void)args;
    return PyBool_FromLong(g_calibrated);
}

/* ============================================================================
 * Module Definition
 * ============================================================================ */

static PyMethodDef module_methods[] = {
    {"spin_delay_ns", py_spin_delay_ns, METH_VARARGS, py_spin_delay_ns_doc},
    {"get_clock_overhead_ns", py_get_clock_overhead_ns, METH_NOARGS,
     py_get_clock_overhead_ns_doc},
    {"get_min_delay_ns", py_get_min_delay_ns, METH_NOARGS, py_get_min_delay_ns_doc},
    {"is_calibrated", py_is_calibrated, METH_NOARGS, py_is_calibrated_doc},
    {NULL, NULL, 0, NULL}
};

PyDoc_STRVAR(module_doc,
"Speed Bump core C extension.\n"
"\n"
"Provides low-level primitives for selective Python slowdown:\n"
"- Clock calibration\n"
"- Spin delay implementation\n"
"- PEP 669 monitoring hooks (future)\n"
"\n"
"Thread Safety:\n"
"- spin_delay_ns() is thread-safe and can run without the GIL\n"
"- Calibration is performed once at module load time\n"
);

/* Multi-phase initialization for Python 3.12+ and FTP support */
static int module_exec(PyObject *module) {
    /* Run calibration at module initialization */
    calibrate_clock();

    /* Add version constant */
    if (PyModule_AddStringConstant(module, "__version__", "0.1.0") < 0) {
        return -1;
    }

    return 0;
}

static PyModuleDef_Slot module_slots[] = {
    {Py_mod_exec, module_exec},
#ifdef Py_mod_gil
    /* Python 3.13+: Declare this module is safe without the GIL.
     * The spin_delay_ns function uses only local variables and is thread-safe.
     * The global calibration state is written once at init time and read-only thereafter.
     */
    {Py_mod_gil, Py_MOD_GIL_NOT_USED},
#endif
    {0, NULL}
};

static struct PyModuleDef module_def = {
    PyModuleDef_HEAD_INIT,
    .m_name = "_core",
    .m_doc = module_doc,
    .m_size = 0,  /* No per-module state */
    .m_methods = module_methods,
    .m_slots = module_slots,
};

PyMODINIT_FUNC PyInit__core(void) {
    return PyModuleDef_Init(&module_def);
}
