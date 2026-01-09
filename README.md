import os

os.environ["OTEL_PYTHON_CONTEXT"] = "contextvars"
os.environ["OTEL_PYTHON_DISABLED"] = "true"