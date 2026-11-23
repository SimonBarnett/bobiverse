# BOB-43 intervene keep queue moving

When stall alerts are non-empty, the tray calls `Invoke-BobQueueIntervene` after the BOB-42 stall-fr path.

The intervene playbook writes `queue-intervene.nudge` under the start-worker dir and logs `queue-intervene action=nudge-under-cap-fill`. A fresh nudge clears the under-cap fill cooldown so a seat req can be queued while offerable work remains.