"""Shared PostgreSQL runtime used by feature-owned repositories."""

from .postgres import PostgresDatabase

__all__ = ["PostgresDatabase"]
