/*
 * Speed Bump - setprofile-based monitoring for Python 3.10
 *
 * This module provides sys.setprofile-based function call monitoring
 * for Python versions before PEP 669 (sys.monitoring).
 *
 * Key challenge: Python 3.10 lacks co_qualname on code objects.
 * We construct qualified names by checking if the first argument
 * is 'self' or 'cls' and extracting the type name.
 */

#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <frameobject.h>
#include <time.h>
#include <stdint.h>
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
 * ============================================================================ */

/* Index for storing match cache in code object's co_extra */
static Py_ssize_t g_extra_index = -1;

/* Cached references to Python objects */
static PyObject *g_patterns_module = NULL;
static PyObject *g_matches_any_func = NULL;
static PyObject *g_target_patterns = NULL;  /* List of TargetPattern objects */

/* Configuration */
static uint64_t g_delay_ns = 0;
static int g_frequency = 1;
static int64_t g_start_ns = 0;
static int64_t g_end_ns = 0;  /* 0 = no end time */
static bool g_installed = false;

/* Thread-local call counters would require more complex handling.
 * For simplicity, we use a global dict (with GIL protection). */
static PyObject *g_call_counters = NULL;

/* Cache entry values stored in co_extra */
#define CACHE_UNKNOWN  ((void*)0)
#define CACHE_NO_MATCH ((void*)1)
#define CACHE_MATCH    ((void*)2)

/* ============================================================================
 * Time Utilities (duplicated from _core.c for independence)
 * ============================================================================ */

static inline uint64_t timespec_to_ns(const struct timespec *ts) {
    return (uint64_t)ts->tv_sec * 1000000000ULL + (uint64_t)ts->tv_nsec;
}

static inline int64_t get_time_ns(void) {
    struct timespec ts;
    clock_gettime(CLOCK_REALTIME, &ts);
    return (int64_t)timespec_to_ns(&ts);
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
 * Qualified Name Construction
 *
 * Python 3.10 lacks co_qualname. We construct it by:
 * 1. Check if co_varnames[0] is "self" or "cls"
 * 2. If so, get the first local from the frame and extract its type name
 * 3. Return "ClassName.method_name" for methods, just "func_name" otherwise
 * ============================================================================ */

static PyObject* get_qualified_name(PyFrameObject *frame, PyCodeObject *code) {
    PyObject *co_name = code->co_name;
    PyObject *co_varnames = code->co_varnames;

    /* Check if this looks like a method (has at least one local) */
    if (code->co_argcount > 0 && PyTuple_GET_SIZE(co_varnames) > 0) {
        PyObject *first_var = PyTuple_GET_ITEM(co_varnames, 0);

        if (PyUnicode_Check(first_var)) {
            const char *var_name = PyUnicode_AsUTF8(first_var);

            if (var_name && (strcmp(var_name, "self") == 0 || strcmp(var_name, "cls") == 0)) {
                /* This is likely a method - get the first argument */
                /* In Python 3.10, frame->f_localsplus contains locals */
                PyObject *first_arg = frame->f_localsplus[0];

                if (first_arg != NULL) {
                    PyTypeObject *arg_type;

                    if (strcmp(var_name, "cls") == 0 && PyType_Check(first_arg)) {
                        /* cls argument is the class itself */
                        arg_type = (PyTypeObject *)first_arg;
                    } else {
                        /* self argument - get its type */
                        arg_type = Py_TYPE(first_arg);
                    }

                    const char *type_name = arg_type->tp_name;
                    /* Strip module prefix if present (e.g., "module.ClassName" -> "ClassName") */
                    const char *dot = strrchr(type_name, '.');
                    if (dot != NULL) {
                        type_name = dot + 1;
                    }

                    /* Construct "ClassName.method_name" */
                    return PyUnicode_FromFormat("%s.%U", type_name, co_name);
                }
            }
        }
    }

    /* Not a method or couldn't determine class - just return function name */
    Py_INCREF(co_name);
    return co_name;
}

/* ============================================================================
 * Pattern Matching
 *
 * Calls into Python's _patterns.matches_any() for simplicity.
 * Returns: 1 = match, 0 = no match, -1 = error
 * ============================================================================ */

static int check_pattern_match(PyObject *module_name, PyObject *qualified_name) {
    if (g_matches_any_func == NULL || g_target_patterns == NULL) {
        return 0;
    }

    PyObject *result = PyObject_CallFunctionObjArgs(
        g_matches_any_func, g_target_patterns, module_name, qualified_name, NULL
    );

    if (result == NULL) {
        PyErr_Clear();  /* Don't propagate errors from pattern matching */
        return 0;
    }

    int matches = PyObject_IsTrue(result);
    Py_DECREF(result);
    return matches;
}

/* ============================================================================
 * Profile Callback
 * ============================================================================ */

static int profile_callback(PyObject *obj, PyFrameObject *frame, int what, PyObject *arg) {
    (void)obj;
    (void)arg;

    /* Only handle call events */
    if (what != PyTrace_CALL) {
        return 0;
    }

    PyCodeObject *code = frame->f_code;
    if (code == NULL) {
        return 0;
    }

    /* Check cache first */
    void *cache_value = CACHE_UNKNOWN;
    if (g_extra_index >= 0) {
        if (_PyCode_GetExtra((PyObject *)code, g_extra_index, &cache_value) < 0) {
            PyErr_Clear();
            cache_value = CACHE_UNKNOWN;
        }
    }

    if (cache_value == CACHE_NO_MATCH) {
        return 0;  /* Known non-match */
    }

    bool is_match;

    if (cache_value == CACHE_MATCH) {
        is_match = true;
    } else {
        /* Compute match */
        PyObject *module_name = code->co_filename;  /* Use filename for module matching */
        PyObject *qualified_name = get_qualified_name(frame, code);

        if (qualified_name == NULL) {
            PyErr_Clear();
            return 0;
        }

        int match_result = check_pattern_match(module_name, qualified_name);
        Py_DECREF(qualified_name);

        is_match = (match_result > 0);

        /* Cache the result */
        if (g_extra_index >= 0) {
            void *new_cache = is_match ? CACHE_MATCH : CACHE_NO_MATCH;
            if (_PyCode_SetExtra((PyObject *)code, g_extra_index, new_cache) < 0) {
                PyErr_Clear();
            }
        }

        if (!is_match) {
            return 0;
        }
    }

    /* Check timing window */
    int64_t now_ns = get_time_ns();

    if (now_ns < g_start_ns) {
        return 0;  /* Before start time */
    }

    if (g_end_ns > 0 && now_ns >= g_end_ns) {
        return 0;  /* After end time */
    }

    /* Handle frequency: only delay every Nth call */
    if (g_frequency > 1 && g_call_counters != NULL) {
        PyObject *code_id = PyLong_FromVoidPtr((void *)code);
        if (code_id == NULL) {
            PyErr_Clear();
            return 0;
        }

        PyObject *count_obj = PyDict_GetItem(g_call_counters, code_id);
        long count = 1;

        if (count_obj != NULL && PyLong_Check(count_obj)) {
            count = PyLong_AsLong(count_obj) + 1;
        }

        PyObject *new_count = PyLong_FromLong(count);
        if (new_count != NULL) {
            PyDict_SetItem(g_call_counters, code_id, new_count);
            Py_DECREF(new_count);
        }
        Py_DECREF(code_id);

        if (count % g_frequency != 0) {
            return 0;  /* Not the Nth call */
        }
    }

    /* Apply delay */
    spin_delay_ns(g_delay_ns);

    return 0;
}

/* ============================================================================
 * Python API
 * ============================================================================ */

PyDoc_STRVAR(install_doc,
"install_setprofile(config)\n"
"\n"
"Install setprofile-based monitoring.\n"
"\n"
"Args:\n"
"    config: A dict with keys:\n"
"        - targets: List of TargetPattern objects\n"
"        - delay_ns: Delay in nanoseconds (int)\n"
"        - frequency: Trigger every Nth call (int, default 1)\n"
"        - start_ns: Start time in nanoseconds (int, optional)\n"
"        - end_ns: End time in nanoseconds (int, optional, 0 = no end)\n"
);

static PyObject* py_install_setprofile(PyObject *self, PyObject *args) {
    (void)self;
    PyObject *config;

    if (!PyArg_ParseTuple(args, "O!", &PyDict_Type, &config)) {
        return NULL;
    }

    if (g_installed) {
        PyErr_SetString(PyExc_RuntimeError, "setprofile monitoring already installed");
        return NULL;
    }

    /* Extract configuration */
    PyObject *targets = PyDict_GetItemString(config, "targets");
    PyObject *delay_obj = PyDict_GetItemString(config, "delay_ns");
    PyObject *freq_obj = PyDict_GetItemString(config, "frequency");
    PyObject *start_obj = PyDict_GetItemString(config, "start_ns");
    PyObject *end_obj = PyDict_GetItemString(config, "end_ns");

    if (targets == NULL || !PyList_Check(targets)) {
        PyErr_SetString(PyExc_ValueError, "config['targets'] must be a list");
        return NULL;
    }

    if (delay_obj == NULL || !PyLong_Check(delay_obj)) {
        PyErr_SetString(PyExc_ValueError, "config['delay_ns'] must be an integer");
        return NULL;
    }

    g_delay_ns = PyLong_AsUnsignedLongLong(delay_obj);
    if (PyErr_Occurred()) {
        return NULL;
    }

    g_frequency = 1;
    if (freq_obj != NULL && PyLong_Check(freq_obj)) {
        g_frequency = (int)PyLong_AsLong(freq_obj);
        if (g_frequency < 1) g_frequency = 1;
    }

    g_start_ns = 0;
    if (start_obj != NULL && PyLong_Check(start_obj)) {
        g_start_ns = PyLong_AsLongLong(start_obj);
    }

    g_end_ns = 0;
    if (end_obj != NULL && PyLong_Check(end_obj)) {
        g_end_ns = PyLong_AsLongLong(end_obj);
    }

    /* Store targets reference */
    Py_XDECREF(g_target_patterns);
    Py_INCREF(targets);
    g_target_patterns = targets;

    /* Import pattern matching function */
    if (g_patterns_module == NULL) {
        g_patterns_module = PyImport_ImportModule("speed_bump._patterns");
        if (g_patterns_module == NULL) {
            return NULL;
        }
    }

    if (g_matches_any_func == NULL) {
        g_matches_any_func = PyObject_GetAttrString(g_patterns_module, "matches_any");
        if (g_matches_any_func == NULL) {
            return NULL;
        }
    }

    /* Initialize call counters dict */
    if (g_frequency > 1) {
        Py_XDECREF(g_call_counters);
        g_call_counters = PyDict_New();
        if (g_call_counters == NULL) {
            return NULL;
        }
    }

    /* Get extra index for caching */
    if (g_extra_index < 0) {
        g_extra_index = _PyEval_RequestCodeExtraIndex(NULL);
        if (g_extra_index < 0) {
            PyErr_SetString(PyExc_RuntimeError, "Failed to get code extra index");
            return NULL;
        }
    }

    /* Install the profile function */
    PyEval_SetProfile(profile_callback, NULL);

    g_installed = true;
    Py_RETURN_NONE;
}

PyDoc_STRVAR(uninstall_doc,
"uninstall_setprofile()\n"
"\n"
"Uninstall setprofile-based monitoring.\n"
);

static PyObject* py_uninstall_setprofile(PyObject *self, PyObject *args) {
    (void)self;
    (void)args;

    if (!g_installed) {
        Py_RETURN_NONE;
    }

    /* Remove profile function */
    PyEval_SetProfile(NULL, NULL);

    /* Clean up */
    Py_CLEAR(g_target_patterns);
    Py_CLEAR(g_call_counters);

    g_installed = false;
    Py_RETURN_NONE;
}

PyDoc_STRVAR(is_installed_doc,
"is_installed_setprofile()\n"
"\n"
"Check if setprofile-based monitoring is installed.\n"
"\n"
"Returns:\n"
"    bool: True if monitoring is installed.\n"
);

static PyObject* py_is_installed_setprofile(PyObject *self, PyObject *args) {
    (void)self;
    (void)args;
    return PyBool_FromLong(g_installed);
}

/* ============================================================================
 * Module Definition
 * ============================================================================ */

static PyMethodDef module_methods[] = {
    {"install_setprofile", py_install_setprofile, METH_VARARGS, install_doc},
    {"uninstall_setprofile", py_uninstall_setprofile, METH_NOARGS, uninstall_doc},
    {"is_installed_setprofile", py_is_installed_setprofile, METH_NOARGS, is_installed_doc},
    {NULL, NULL, 0, NULL}
};

PyDoc_STRVAR(module_doc,
"Speed Bump setprofile-based monitoring for Python 3.10.\n"
"\n"
"This module provides sys.setprofile-based function call monitoring\n"
"for Python versions that don't support PEP 669 (sys.monitoring).\n"
"\n"
"The key difference from the PEP 669 backend is that we must construct\n"
"qualified names manually since Python 3.10 lacks co_qualname.\n"
);

static struct PyModuleDef module_def = {
    PyModuleDef_HEAD_INIT,
    .m_name = "_setprofile",
    .m_doc = module_doc,
    .m_size = -1,  /* Module has global state */
    .m_methods = module_methods,
};

PyMODINIT_FUNC PyInit__setprofile(void) {
    return PyModule_Create(&module_def);
}
