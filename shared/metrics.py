"""CloudWatch Embedded Metric Format (EMF) emitter.

EMF metrics are extracted from log lines by CloudWatch, avoiding synchronous
``PutMetricData`` calls. Dimensions are deliberately low-cardinality (service
and outcome only) to avoid custom-metric cost explosions.
"""

from __future__ import annotations

import json
import os
import sys
import time

NAMESPACE = "NovaBank/Banking"


def emit(metric: str, value: float = 1, *, unit: str = "Count", **dimensions: str) -> None:
    dims = {"Service": os.environ.get("SERVICE_NAME", "novabank"), **dimensions}
    doc = {
        "_aws": {
            "Timestamp": int(time.time() * 1000),
            "CloudWatchMetrics": [
                {"Namespace": NAMESPACE, "Dimensions": [sorted(dims)], "Metrics": [{"Name": metric, "Unit": unit}]}
            ],
        },
        metric: value,
        **dims,
    }
    sys.stdout.write(json.dumps(doc, separators=(",", ":")) + "\n")
