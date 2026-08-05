# homelab-map

Loads and refreshes the personal homelab context layer from three complementary sources:

- version-controlled Compose and SWAG configuration for desired state;
- specialized `~/docs/scripts` inventories for observed domain state;
- the compiled `~/.homelab` topology map and source manifest.

Run `scripts/refresh-context.py` to refresh the source layer and compiled overview before answering questions that depend on current state.
