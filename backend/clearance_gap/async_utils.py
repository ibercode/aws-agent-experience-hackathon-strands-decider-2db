"""Cancellation boundaries for work that continues outside the caller's task."""
import asyncio


class SettledCancellation(asyncio.CancelledError):
    """The caller was cancelled, but the protected operation completed successfully."""


async def settle_before_cancel(awaitable):
    """Retain ownership until a transaction or active HTTP request has settled.

    Cancelling to_thread does not stop its transaction. Likewise disconnecting an
    inference client does not stop the model server. Shield the operation, consume
    its result, then propagate cancellation; callers must retain committed state.
    """
    operation = asyncio.ensure_future(awaitable)
    cancelled = False
    while not operation.done():
        try:
            await asyncio.shield(operation)
        except asyncio.CancelledError:
            cancelled = True
    result = operation.result()
    if cancelled:
        raise SettledCancellation()
    return result
