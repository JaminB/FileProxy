# EFS resources removed — write cache now uses a local Docker named volume
# (fileproxy-write-cache) shared between the app and Celery worker containers
# on the same EC2 host.  EFS bursting-mode throughput was ~1 MiB/s for this
# near-empty filesystem, making every upload block for seconds per MB.
