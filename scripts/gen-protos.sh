#!/bin/sh
# Generate Python gRPC stubs from OpenShell v0.1.2 protos.
set -eu
cd "$(dirname "$0")/.."
OUT=src/openshell_teams/gen
uv run python -m grpc_tools.protoc -I proto/openshell --python_out=$OUT --grpc_python_out=$OUT --pyi_out=$OUT proto/openshell/extension.proto proto/openshell/supervisor_middleware.proto proto/openshell/gateway_interceptor.proto
# make imports package-relative
sed -i '' 's/^import extension_pb2/from . import extension_pb2/; s/^import supervisor_middleware_pb2/from . import supervisor_middleware_pb2/; s/^import gateway_interceptor_pb2/from . import gateway_interceptor_pb2/' $OUT/*_pb2*.py
touch $OUT/__init__.py
