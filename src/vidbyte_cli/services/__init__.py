"""Feature services: the layer between a command and the shared substrate in `lib/`.

A service owns one product's algorithm end to end. It may import from `lib/`; nothing in
`lib/` may import from here, and no service may import a command.
"""
