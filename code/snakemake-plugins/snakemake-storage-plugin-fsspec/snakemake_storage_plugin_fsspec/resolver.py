"""URL resolver protocol and registry for fsspec storage plugin.

Resolvers translate local file paths to remote URLs that can be
accessed via fsspec. This enables transparent remote access for
files managed by systems like git-annex or datalad.

Example:
    class MyResolver(URLResolver):
        def resolve(self, path: Path) -> str | None:
            # Look up URL in your system
            return "https://example.com/files/" + path.name

        def priority(self) -> int:
            return 10  # Lower = higher priority

    registry = URLResolverRegistry()
    registry.register(MyResolver())
    url = registry.resolve(Path("data.txt"))
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, Protocol, runtime_checkable


@runtime_checkable
class URLResolver(Protocol):
    """Protocol for URL resolvers.

    Implementations translate local file paths to remote URLs.
    Multiple resolvers can be registered; they are tried in
    priority order until one returns a URL.
    """

    def resolve(self, path: Path, cwd: Optional[Path] = None) -> Optional[str]:
        """Resolve a local path to a remote URL.

        Args:
            path: Local file path to resolve
            cwd: Working directory context (optional)

        Returns:
            Remote URL string, or None if cannot resolve
        """
        ...

    def priority(self) -> int:
        """Return resolver priority (lower = higher priority).

        Resolvers are tried in ascending priority order.
        Suggested ranges:
            0-9: Critical/override resolvers
            10-49: Primary resolvers (e.g., git-annex)
            50-99: Fallback resolvers
            100+: Last resort
        """
        ...

    def name(self) -> str:
        """Return resolver name for logging/debugging."""
        ...


class BaseResolver(ABC):
    """Base class for URL resolvers with common functionality."""

    _priority: int = 50
    _name: str = "base"

    def __init__(self, priority: Optional[int] = None, name: Optional[str] = None):
        """Initialize resolver.

        Args:
            priority: Override default priority
            name: Override default name
        """
        if priority is not None:
            self._priority = priority
        if name is not None:
            self._name = name

    def priority(self) -> int:
        return self._priority

    def name(self) -> str:
        return self._name

    @abstractmethod
    def resolve(self, path: Path, cwd: Optional[Path] = None) -> Optional[str]:
        """Resolve path to URL. Must be implemented by subclasses."""
        ...


class URLResolverRegistry:
    """Registry for URL resolvers.

    Manages multiple resolvers and tries them in priority order.
    """

    def __init__(self):
        self._resolvers: list[URLResolver] = []

    def register(self, resolver: URLResolver) -> None:
        """Register a URL resolver.

        Args:
            resolver: Resolver instance to register
        """
        self._resolvers.append(resolver)
        # Keep sorted by priority
        self._resolvers.sort(key=lambda r: r.priority())

    def unregister(self, resolver: URLResolver) -> bool:
        """Unregister a URL resolver.

        Args:
            resolver: Resolver instance to remove

        Returns:
            True if removed, False if not found
        """
        try:
            self._resolvers.remove(resolver)
            return True
        except ValueError:
            return False

    def resolve(self, path: Path, cwd: Optional[Path] = None) -> Optional[str]:
        """Resolve a path using registered resolvers.

        Tries resolvers in priority order, returns first successful result.

        Args:
            path: Path to resolve
            cwd: Working directory context

        Returns:
            URL string or None if no resolver succeeded
        """
        for resolver in self._resolvers:
            try:
                url = resolver.resolve(path, cwd)
                if url is not None:
                    return url
            except Exception:
                # Log but continue to next resolver
                continue
        return None

    def list_resolvers(self) -> list[tuple[str, int]]:
        """List registered resolvers with their priorities.

        Returns:
            List of (name, priority) tuples
        """
        return [(r.name(), r.priority()) for r in self._resolvers]

    def clear(self) -> None:
        """Remove all registered resolvers."""
        self._resolvers.clear()


# Global registry instance
_global_registry = URLResolverRegistry()


def get_global_registry() -> URLResolverRegistry:
    """Get the global URL resolver registry."""
    return _global_registry


def register_resolver(resolver: URLResolver) -> None:
    """Register a resolver in the global registry."""
    _global_registry.register(resolver)


def resolve_url(path: Path, cwd: Optional[Path] = None) -> Optional[str]:
    """Resolve a path using the global registry."""
    return _global_registry.resolve(path, cwd)
