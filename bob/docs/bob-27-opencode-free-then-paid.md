# BOB-27 Workers > Open Code free then paid

FR #8730. Workers > Open Code reads `BOB_OPENCODE_FUEL_FILE` or `run/opencode-fuel.json` (`free` and `paid` integers).

- `free` above 0 logs `workers-opencode slot=free` and starts the free model.
- `free` at 0 or below and `paid` above 0 logs `workers-opencode slot=paid reason=free-exhausted` and starts the paid model.
- A missing file stays on free. An explicit paid menu row stays paid.
