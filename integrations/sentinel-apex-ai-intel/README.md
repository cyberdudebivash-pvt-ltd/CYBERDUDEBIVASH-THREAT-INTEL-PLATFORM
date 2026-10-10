# SENTINEL APEX AI intel adapter

Independent upstream adapter for `sentinel-apex.intel.v1`.

It does not open the Threat Intel database, replace the production ingestion pipeline, or publish a second copy of a threat. Callers keep the returned state in their own store. Original master ids, canonical URLs, CVSS, KEV flags, verification state, and source timestamps are copied as supplied. They are not rewritten here.

`unattributed` evidence becomes `unresolved` and is excluded from corroboration. Non-CLEAR TLP is rejected. A bad page does not advance the cursor. A `visible: false` event removes the local copy.

This package is not imported by the platform runtime. Its unit test passing is not a production integration. Host CI was not run from the engine workspace.
