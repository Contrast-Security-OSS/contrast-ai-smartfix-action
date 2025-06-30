"""
This module provides a patch to suppress the "Event loop is closed" error on Windows.

For more details, see: https://github.com/python/cpython/issues/83413
"""

import asyncio
import platform
import warnings
from asyncio.proactor_events import _ProactorBasePipeTransport

def apply_asyncio_win_patch():
    """
    Applies a monkey-patch to asyncio to avoid the "Event loop is closed" error on Windows.
    """
    if platform.system() == "Windows":
        # Patch for the "Event loop is closed" error in BaseEventLoop._check_closed
        _original_loop_check_closed = asyncio.BaseEventLoop._check_closed
        def _patched_loop_check_closed(self):
            try:
                _original_loop_check_closed(self)
            except RuntimeError as e:
                if "Event loop is closed" in str(e):
                    return  # Suppress the error
                raise
        asyncio.BaseEventLoop._check_closed = _patched_loop_check_closed

        # Patch for the "unclosed transport" warning in _ProactorBasePipeTransport.__del__
        def _patched_del(self, _warn=warnings.warn):
            if self._loop and not self._loop.is_closed():
                _warn(f"unclosed transport {self!r}", ResourceWarning, source=self)
                self.close()
        _ProactorBasePipeTransport.__del__ = _patched_del
