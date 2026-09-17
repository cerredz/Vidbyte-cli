The round limit bounds how many complete critic-to-generator refinement cycles may improve the candidate slate. It accepts one through eight rounds, while two rounds usually balance refinement against latency and model usage. Every round lets an independent critic return one block of whole-slate signal, then lets the persistent generator use that signal at its discretion.

A single round suits simple goals with clear context, while eight allows difficult ideas several refinement opportunities. The workflow computes this loop shape rather than asking the model when to stop, and it ends early when the slate is unchanged.

The limit applies to complete refinements after each initial review. Values outside the supported range are rejected before model work begins, and token or timeout limits still stop the run first.
