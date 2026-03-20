"""ADK Asyncio Workarounds

Google ADK has issues with asyncio event loop cleanup (observed through v1.5.0).
This module centralizes all workarounds so main.py stays focused on orchestration.

Call apply_asyncio_workarounds() once at module startup and cleanup_event_loop()
at the end of main() before exit.
"""

import sys
import asyncio
import warnings
import atexit
import platform
from asyncio.proactor_events import _ProactorBasePipeTransport

from src.utils import debug_log


def apply_asyncio_workarounds():
    """Apply all ADK asyncio workarounds and register atexit cleanup. Call once at startup."""
    _suppress_resource_warnings()
    _patch_check_closed()
    if platform.system() == 'Windows':
        _patch_pipe_transport()
        _patch_subprocess_transport()
    atexit.register(_cleanup_asyncio)


def cleanup_event_loop():
    """Cancel pending tasks and close the event loop. Call at end of main() before exit."""
    try:
        loop = asyncio.get_event_loop_policy().get_event_loop()
        if not loop.is_closed():
            pending = asyncio.all_tasks(loop)
            if pending:
                for task in pending:
                    try:
                        task.cancel()
                    except Exception:
                        pass

                try:
                    loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                except (asyncio.CancelledError, Exception):
                    pass

            try:
                loop.run_until_complete(loop.shutdown_asyncgens())
            except Exception:
                pass

            try:
                loop.close()
            except Exception:
                pass

        if platform.system() == 'Windows':
            try:
                import gc
                gc.collect()
            except Exception:
                pass
    except Exception as e:
        debug_log(f"Ignoring error during asyncio cleanup: {str(e)}")


def _suppress_resource_warnings():
    """Suppress asyncio ResourceWarnings that fire during ADK shutdown."""
    warnings.filterwarnings("ignore", category=ResourceWarning,
                            message="unclosed.*<asyncio.sslproto._SSLProtocolTransport.*")
    warnings.filterwarnings("ignore", category=ResourceWarning,
                            message="unclosed transport")
    warnings.filterwarnings("ignore", category=ResourceWarning,
                            message="unclosed.*<asyncio.*")


def _patch_check_closed():
    """Suppress spurious 'Event loop is closed' RuntimeErrors during shutdown."""
    _original = asyncio.base_events.BaseEventLoop._check_closed

    def _patched(self):
        try:
            _original(self)
        except RuntimeError as e:
            if "Event loop is closed" in str(e):
                return
            raise

    asyncio.BaseEventLoop._check_closed = _patched


def _patch_pipe_transport():
    """Patch _ProactorBasePipeTransport.__del__ to avoid Windows shutdown errors."""
    try:
        _original = _ProactorBasePipeTransport.__del__

        def _patched(self):
            try:
                if self._loop.is_closed() or sys.is_finalizing():
                    return
                _original(self)
            except (AttributeError, RuntimeError, ImportError, TypeError):
                pass

        _ProactorBasePipeTransport.__del__ = _patched
        debug_log("Successfully patched _ProactorBasePipeTransport.__del__ for Windows")
    except (ImportError, AttributeError) as e:
        debug_log(f"Could not patch _ProactorBasePipeTransport: {str(e)}")


def _patch_subprocess_transport():
    """Patch BaseSubprocessTransport.__del__ to avoid Windows shutdown errors."""
    try:
        from asyncio.base_subprocess import BaseSubprocessTransport
        _original = BaseSubprocessTransport.__del__

        def _patched(self):
            try:
                if hasattr(self, '_loop') and self._loop is not None and (self._loop.is_closed() or sys.is_finalizing()):
                    return
                _original(self)
            except (AttributeError, RuntimeError, ImportError, TypeError, ValueError):
                pass

        BaseSubprocessTransport.__del__ = _patched
        debug_log("Successfully patched BaseSubprocessTransport.__del__ for Windows")
    except (ImportError, AttributeError) as e:
        debug_log(f"Could not patch BaseSubprocessTransport: {str(e)}")


def _cleanup_asyncio():  # noqa: C901
    """
    Atexit handler: properly close asyncio resources to prevent shutdown noise.
    On Windows, stderr is suppressed to avoid printing residual errors.
    """
    original_stderr = sys.stderr
    try:
        class _DummyStderr:
            def write(self, *args, **kwargs):
                pass

            def flush(self):
                pass

        if platform.system() == 'Windows':
            sys.stderr = _DummyStderr()
            try:
                loop_policy = asyncio.get_event_loop_policy()
                try:
                    loop = loop_policy.get_event_loop()
                    if not loop.is_closed():
                        if loop.is_running():
                            loop.stop()

                        pending = asyncio.all_tasks(loop)
                        if pending:
                            for task in pending:
                                task.cancel()
                            try:
                                loop.run_until_complete(asyncio.wait_for(
                                    asyncio.gather(*pending, return_exceptions=True),
                                    timeout=1.0
                                ))
                            except (asyncio.CancelledError, asyncio.TimeoutError, Exception):
                                pass

                        try:
                            loop.run_until_complete(loop.shutdown_asyncgens())
                        except Exception:
                            pass

                        try:
                            loop.close()
                        except Exception:
                            pass
                except Exception:
                    pass

                try:
                    import gc
                    gc.collect()
                except Exception:
                    pass
            except Exception:
                pass
        else:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.stop()

                pending = asyncio.all_tasks(loop)
                if pending:
                    for task in pending:
                        task.cancel()

                    if not loop.is_closed():
                        loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))

                if not loop.is_closed():
                    loop.run_until_complete(loop.shutdown_asyncgens())
                    loop.close()
            except Exception:
                pass
    finally:
        sys.stderr = original_stderr
