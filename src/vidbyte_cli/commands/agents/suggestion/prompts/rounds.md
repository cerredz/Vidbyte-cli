The round limit bounds how many critique-and-curation passes may improve the active suggestion slate. Two rounds usually balance refinement against latency and model usage.

A single round suits simple goals with clear context, while three allows borderline ideas another curation opportunity. The workflow computes this loop shape rather than asking the model when to stop.

The limit applies to critique-and-curation passes after initial generation. Values outside the supported range are rejected before model work begins.
