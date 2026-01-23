"""Setup script for speed-bump C extension."""

from setuptools import Extension, setup

extra_compile_args = ["-O3", "-Wall", "-Wextra", "-std=c11"]

ext_modules = [
    Extension(
        "speed_bump._core",
        sources=["src/speed_bump/_core.c"],
        extra_compile_args=extra_compile_args,
        define_macros=[("_GNU_SOURCE", "1")],
    ),
]

setup(ext_modules=ext_modules)
