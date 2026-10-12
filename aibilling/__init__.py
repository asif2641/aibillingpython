"""
aibilling/__init__.py
======================
Django project package.
"""

# Compatibility patch for Django BaseContext.__copy__ on Python 3.14+
try:
    from django.template.context import BaseContext

    def _safe_base_context_copy(self):
        duplicate = self.__class__.__new__(self.__class__)
        duplicate.dicts = self.dicts[:]
        return duplicate

    BaseContext.__copy__ = _safe_base_context_copy
except ImportError:
    pass
