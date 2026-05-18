# -
# #%L
# Contrast AI SmartFix
# %%
# Copyright (C) 2026 Contrast Security, Inc.
# %%
# Contact: support@contrastsecurity.com
# License: Commercial
# NOTICE: This Software and the patented inventions embodied within may only be
# used as part of Contrast Security's commercial offerings. Even though it is
# made available through public repositories, use of this Software is subject to
# the applicable End User Licensing Agreement found at
# https://www.contrastsecurity.com/enduser-terms-0317a or as otherwise agreed
# between Contrast Security and the End User. The Software may not be reverse
# engineered, modified, repackaged, sold, redistributed or otherwise used in a
# way not consistent with the End User License Agreement.
# #L%
#

"""
Propagation tests: TokenBalanceExhaustedError must travel from the LLM call
path through every agent layer up to main.py without being swallowed.

Production raise site:
    smartfix_litellm._call_llm_with_retry (HTTP 402 → TokenBalanceExhaustedError)

Layers it must pass through unswallowed:
    sub_agent_executor.SubAgentExecutor.execute_agent  (line ~342, except Exception)
    smartfix_agent.SmartFixAgent._run_ai_fix_agent     (line ~170, except Exception)
    smartfix_agent.SmartFixAgent._run_fix_agent        (line ~136, except Exception)
    smartfix_agent.SmartFixAgent.remediate             (line ~67,  except Exception)

These tests fail today because each swallower converts the exception to
error_exit (sys.exit) or an AGENT_FAILURE session result. They pass once
each catch-all explicitly re-raises TokenBalanceExhaustedError.
"""

import asyncio
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, AsyncMock

sys.path.insert(0, str(Path(__file__).parent))

from src.smartfix.domains.agents.smartfix_agent import SmartFixAgent  # noqa: E402
from src.smartfix.domains.agents.sub_agent_executor import SubAgentExecutor  # noqa: E402
from src.smartfix.shared.exceptions import TokenBalanceExhaustedError  # noqa: E402
from setup_test_env import make_sample_context  # noqa: E402


async def _raising_event_stream():
    """Async generator that raises TokenBalanceExhaustedError on first __anext__()."""
    raise TokenBalanceExhaustedError("Token balance exhausted (HTTP 402)")
    yield  # pragma: no cover  -- unreachable, makes this an async generator


class _SubprocessIsolatedTestCase(unittest.TestCase):
    """
    Base: mocks subprocess.run so any code path that reaches real git/shell
    commands becomes a no-op. Prevents tests from mutating the working repo
    if a swallower routes through error_exit → GitOperations.cleanup_branch
    before the fix is applied.
    """

    def setUp(self):
        self._subproc_patcher = patch('subprocess.run')
        mock_subprocess = self._subproc_patcher.start()
        mock_subprocess.return_value = SimpleNamespace(
            returncode=0,
            stdout="",
            communicate=lambda: (b"", b""),
        )

    def tearDown(self):
        self._subproc_patcher.stop()


class TestSubAgentExecutorPropagatesTokenBalanceExhausted(_SubprocessIsolatedTestCase):
    """
    Layer: SubAgentExecutor.execute_agent (line ~342 catch-all).

    Simulates the real 402 path: TokenBalanceExhaustedError surfaces inside the
    async event iteration that execute_agent's try block wraps. The catch-all
    must NOT convert it to AGENT_FAILURE / error_exit — it must re-raise.
    """

    def test_execute_agent_reraises_token_balance_exhausted(self):
        executor = SubAgentExecutor(max_events=120)

        async def _raising_create_event_stream(*args, **kwargs):
            return _raising_event_stream()

        with patch.object(
            executor, '_validate_prerequisites',
            new=AsyncMock(return_value=("sid", "uid")),
        ), patch.object(
            executor, '_create_event_stream',
            new=_raising_create_event_stream,
        ), patch.object(
            executor, '_cleanup_event_stream',
            new=AsyncMock(),
        ):
            with self.assertRaises(TokenBalanceExhaustedError):
                asyncio.run(executor.execute_agent(
                    runner=object(),
                    agent=object(),
                    session=object(),
                    user_query="query",
                    remediation_id="rem-402",
                ))


class TestSmartFixAgentPropagatesTokenBalanceExhausted(_SubprocessIsolatedTestCase):
    """
    Layer: SmartFixAgent.remediate → _run_fix_agent → _run_ai_fix_agent.

    These three catch-alls (lines ~67, ~136, ~170) must all let
    TokenBalanceExhaustedError through. _run_ai_fix_agent's catch is the most
    dangerous: today it calls error_exit (sys.exit) which both halts the
    process and prevents the typed exception from reaching main.py.
    """

    def test_remediate_reraises_when_fix_execution_raises_token_balance_exhausted(self):
        agent = SmartFixAgent()
        context = make_sample_context(
            remediation_id="rem-402-smartfix",
            session_id="sess-402-smartfix",
            build_config=None,
        )

        with patch.object(
            agent, '_run_fix_agent_execution',
            side_effect=TokenBalanceExhaustedError("Token balance exhausted (HTTP 402)"),
        ):
            with self.assertRaises(TokenBalanceExhaustedError):
                agent.remediate(context)


if __name__ == "__main__":
    unittest.main()
