"""Runtime package namespace.

Keep this module lightweight to avoid importing chat runtime dependencies
(`sage.flownet`) when only endpoint/runtime management modules are needed.
"""

__all__: list[str] = []
