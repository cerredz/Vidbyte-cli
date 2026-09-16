The round limit bounds how many critique-and-revision cycles may improve the candidate pool. It accepts one through eight rounds, while two rounds usually balance refinement against latency and model usage.

A single round suits simple goals with clear context, while eight allows difficult ideas several revision opportunities. The workflow computes this loop shape rather than asking the model when to stop, and it ends early when the critic has no repair work or a revision is unchanged.

The limit applies to revisions as well as initial review. Values outside the supported range are rejected before model work begins, and token or timeout limits still stop the run first.
