# Configuration boundary

This package owns non-secret CLI configuration and every local state path. `models.py`
defines the version-one allow-list, `resolver.py` applies command → environment → selected
profile → default profile → built-in precedence, and `config.py` performs typed atomic
writes. `paths.py` uses platform-native locations; `migration.py` is the only compatibility
writer for the historical `~/.vidbyte` tree.

Secrets do not belong here. They live behind `lib/auth`, even when a restricted file is the
user-approved fallback. Path discovery never creates directories, and read-only resolution
never triggers migration.
