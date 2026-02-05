"""Tests for the native module (kernel uprobe interface)."""

from __future__ import annotations

import os
from unittest import mock

import pytest

from speed_bump import native


class TestSpecFormatting:
    """Tests for spec string formatting (no kernel module required)."""

    def test_format_add_spec_with_explicit_pid(self) -> None:
        """Test add spec formatting with explicit PID."""
        spec = native.format_add_spec("/usr/bin/python3", "PyObject_GetAttr", 1000, pid=12345)
        assert spec == "+/usr/bin/python3:PyObject_GetAttr 1000 pid=12345"

    def test_format_add_spec_with_default_pid(self) -> None:
        """Test add spec formatting with default (current) PID."""
        spec = native.format_add_spec("/usr/bin/python3", "PyObject_GetAttr", 1000)
        expected_pid = os.getpid()
        assert spec == f"+/usr/bin/python3:PyObject_GetAttr 1000 pid={expected_pid}"

    def test_format_add_spec_zero_delay(self) -> None:
        """Test add spec formatting with zero delay."""
        spec = native.format_add_spec("/path/to/binary", "some_func", 0, pid=1)
        assert spec == "+/path/to/binary:some_func 0 pid=1"

    def test_format_remove_spec(self) -> None:
        """Test remove spec formatting."""
        spec = native.format_remove_spec("/usr/bin/python3", "PyObject_GetAttr")
        assert spec == "-/usr/bin/python3:PyObject_GetAttr"


class TestAddProbe:
    """Tests for add_probe function."""

    def test_add_probe_writes_correct_spec(self) -> None:
        """Test add_probe writes the correct spec to sysfs."""
        with mock.patch("builtins.open", mock.mock_open()) as mock_file:
            native.add_probe("/usr/bin/python3", "PyObject_GetAttr", 1000, pid=42)
            mock_file.assert_called_once_with(native.SYSFS_TARGETS, "w")
            mock_file().write.assert_called_once_with(
                "+/usr/bin/python3:PyObject_GetAttr 1000 pid=42"
            )

    def test_add_probe_uses_current_pid_by_default(self) -> None:
        """Test add_probe uses current PID when not specified."""
        with mock.patch("builtins.open", mock.mock_open()) as mock_file:
            native.add_probe("/usr/bin/python3", "PyObject_GetAttr", 500)
            expected_spec = f"+/usr/bin/python3:PyObject_GetAttr 500 pid={os.getpid()}"
            mock_file().write.assert_called_once_with(expected_spec)


class TestRemoveProbe:
    """Tests for remove_probe function."""

    def test_remove_probe_writes_correct_spec(self) -> None:
        """Test remove_probe writes the correct spec to sysfs."""
        with mock.patch("builtins.open", mock.mock_open()) as mock_file:
            native.remove_probe("/usr/bin/python3", "PyObject_GetAttr")
            mock_file.assert_called_once_with(native.SYSFS_TARGETS, "w")
            mock_file().write.assert_called_once_with("-/usr/bin/python3:PyObject_GetAttr")


class TestProbeContextManager:
    """Tests for the probe context manager."""

    def test_probe_context_manager_adds_and_removes(self) -> None:
        """Test probe context manager adds on entry and removes on exit."""
        with mock.patch("builtins.open", mock.mock_open()) as mock_file:
            with native.probe("/usr/bin/python3", "func", delay_ns=100, pid=123):
                # Inside context - add should have been called
                pass

            # Check both add and remove were called
            calls = mock_file().write.call_args_list
            assert len(calls) == 2
            assert calls[0][0][0] == "+/usr/bin/python3:func 100 pid=123"
            assert calls[1][0][0] == "-/usr/bin/python3:func"

    def test_probe_context_manager_removes_on_exception(self) -> None:
        """Test probe context manager removes even if exception occurs."""
        with mock.patch("builtins.open", mock.mock_open()) as mock_file:
            with pytest.raises(ValueError, match="test exception"):
                with native.probe("/bin/test", "sym", delay_ns=50, pid=1):
                    raise ValueError("test exception")

            # Remove should still have been called
            calls = mock_file().write.call_args_list
            assert len(calls) == 2
            assert calls[1][0][0] == "-/bin/test:sym"


class TestIsAvailable:
    """Tests for is_available function."""

    def test_is_available_returns_false_when_file_missing(self) -> None:
        """Test is_available returns False when sysfs file doesn't exist."""
        with mock.patch("os.path.exists", return_value=False):
            assert native.is_available() is False

    def test_is_available_returns_false_when_not_writable(self) -> None:
        """Test is_available returns False when sysfs file isn't writable."""
        with mock.patch("os.path.exists", return_value=True):
            with mock.patch("os.access", return_value=False):
                assert native.is_available() is False

    def test_is_available_returns_true_when_writable(self) -> None:
        """Test is_available returns True when sysfs file exists and is writable."""
        with mock.patch("os.path.exists", return_value=True):
            with mock.patch("os.access", return_value=True):
                assert native.is_available() is True


class TestModuleExport:
    """Tests for module export from speed_bump package."""

    def test_native_exported_from_package(self) -> None:
        """Test that native module is exported from speed_bump package."""
        import speed_bump
        assert hasattr(speed_bump, "native")
        assert speed_bump.native is native

    def test_native_in_all(self) -> None:
        """Test that 'native' is in __all__."""
        import speed_bump
        assert "native" in speed_bump.__all__


@pytest.mark.skipif(
    not native.is_available(),
    reason="Kernel module not loaded or sysfs interface not available"
)
class TestIntegration:
    """Integration tests requiring the kernel module to be loaded."""

    def test_add_and_remove_probe(self) -> None:
        """Test adding and removing a probe via sysfs."""
        import sys
        python_path = sys.executable

        # This will fail if the symbol doesn't exist, but should succeed
        # if the kernel module is properly loaded
        native.add_probe(python_path, "PyObject_GetAttr", 100)
        native.remove_probe(python_path, "PyObject_GetAttr")
