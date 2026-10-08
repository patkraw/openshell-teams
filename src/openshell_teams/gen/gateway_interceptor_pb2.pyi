from google.protobuf import struct_pb2 as _struct_pb2
import extension_pb2 as _extension_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class GatewayInterceptorPhase(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    GATEWAY_INTERCEPTOR_PHASE_UNSPECIFIED: _ClassVar[GatewayInterceptorPhase]
    GATEWAY_INTERCEPTOR_PHASE_MODIFY_OPERATION: _ClassVar[GatewayInterceptorPhase]
    GATEWAY_INTERCEPTOR_PHASE_VALIDATE: _ClassVar[GatewayInterceptorPhase]
    GATEWAY_INTERCEPTOR_PHASE_POST_COMMIT: _ClassVar[GatewayInterceptorPhase]
GATEWAY_INTERCEPTOR_PHASE_UNSPECIFIED: GatewayInterceptorPhase
GATEWAY_INTERCEPTOR_PHASE_MODIFY_OPERATION: GatewayInterceptorPhase
GATEWAY_INTERCEPTOR_PHASE_VALIDATE: GatewayInterceptorPhase
GATEWAY_INTERCEPTOR_PHASE_POST_COMMIT: GatewayInterceptorPhase

class DescribeRequest(_message.Message):
    __slots__ = ("gateway",)
    GATEWAY_FIELD_NUMBER: _ClassVar[int]
    gateway: _extension_pb2.PeerMetadata
    def __init__(self, gateway: _Optional[_Union[_extension_pb2.PeerMetadata, _Mapping]] = ...) -> None: ...

class InterceptorEvaluation(_message.Message):
    __slots__ = ("interceptor_name", "binding_id", "service", "method", "principal", "modify_operation", "validate", "post_commit")
    class PrincipalEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    INTERCEPTOR_NAME_FIELD_NUMBER: _ClassVar[int]
    BINDING_ID_FIELD_NUMBER: _ClassVar[int]
    SERVICE_FIELD_NUMBER: _ClassVar[int]
    METHOD_FIELD_NUMBER: _ClassVar[int]
    PRINCIPAL_FIELD_NUMBER: _ClassVar[int]
    MODIFY_OPERATION_FIELD_NUMBER: _ClassVar[int]
    VALIDATE_FIELD_NUMBER: _ClassVar[int]
    POST_COMMIT_FIELD_NUMBER: _ClassVar[int]
    interceptor_name: str
    binding_id: str
    service: str
    method: str
    principal: _containers.ScalarMap[str, str]
    modify_operation: ModifyOperationEvaluation
    validate: ValidateEvaluation
    post_commit: PostCommitEvaluation
    def __init__(self, interceptor_name: _Optional[str] = ..., binding_id: _Optional[str] = ..., service: _Optional[str] = ..., method: _Optional[str] = ..., principal: _Optional[_Mapping[str, str]] = ..., modify_operation: _Optional[_Union[ModifyOperationEvaluation, _Mapping]] = ..., validate: _Optional[_Union[ValidateEvaluation, _Mapping]] = ..., post_commit: _Optional[_Union[PostCommitEvaluation, _Mapping]] = ...) -> None: ...

class ModifyOperationEvaluation(_message.Message):
    __slots__ = ("proposed_operation",)
    PROPOSED_OPERATION_FIELD_NUMBER: _ClassVar[int]
    proposed_operation: _struct_pb2.Struct
    def __init__(self, proposed_operation: _Optional[_Union[_struct_pb2.Struct, _Mapping]] = ...) -> None: ...

class ValidateEvaluation(_message.Message):
    __slots__ = ("proposed_operation", "current_state")
    PROPOSED_OPERATION_FIELD_NUMBER: _ClassVar[int]
    CURRENT_STATE_FIELD_NUMBER: _ClassVar[int]
    proposed_operation: _struct_pb2.Struct
    current_state: _struct_pb2.Struct
    def __init__(self, proposed_operation: _Optional[_Union[_struct_pb2.Struct, _Mapping]] = ..., current_state: _Optional[_Union[_struct_pb2.Struct, _Mapping]] = ...) -> None: ...

class PostCommitEvaluation(_message.Message):
    __slots__ = ("committed_response",)
    COMMITTED_RESPONSE_FIELD_NUMBER: _ClassVar[int]
    committed_response: _struct_pb2.Struct
    def __init__(self, committed_response: _Optional[_Union[_struct_pb2.Struct, _Mapping]] = ...) -> None: ...

class InterceptorResult(_message.Message):
    __slots__ = ("allowed", "reason", "status_code", "patches", "log_annotations")
    class LogAnnotationsEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    ALLOWED_FIELD_NUMBER: _ClassVar[int]
    REASON_FIELD_NUMBER: _ClassVar[int]
    STATUS_CODE_FIELD_NUMBER: _ClassVar[int]
    PATCHES_FIELD_NUMBER: _ClassVar[int]
    LOG_ANNOTATIONS_FIELD_NUMBER: _ClassVar[int]
    allowed: bool
    reason: str
    status_code: str
    patches: _containers.RepeatedCompositeFieldContainer[JsonPatch]
    log_annotations: _containers.ScalarMap[str, str]
    def __init__(self, allowed: _Optional[bool] = ..., reason: _Optional[str] = ..., status_code: _Optional[str] = ..., patches: _Optional[_Iterable[_Union[JsonPatch, _Mapping]]] = ..., log_annotations: _Optional[_Mapping[str, str]] = ...) -> None: ...

class InterceptorManifest(_message.Message):
    __slots__ = ("name", "bindings", "failure_policy", "provider_profiles", "expected_audience", "extension")
    NAME_FIELD_NUMBER: _ClassVar[int]
    BINDINGS_FIELD_NUMBER: _ClassVar[int]
    FAILURE_POLICY_FIELD_NUMBER: _ClassVar[int]
    PROVIDER_PROFILES_FIELD_NUMBER: _ClassVar[int]
    EXPECTED_AUDIENCE_FIELD_NUMBER: _ClassVar[int]
    EXTENSION_FIELD_NUMBER: _ClassVar[int]
    name: str
    bindings: _containers.RepeatedCompositeFieldContainer[InterceptorBinding]
    failure_policy: str
    provider_profiles: bool
    expected_audience: str
    extension: _extension_pb2.PeerMetadata
    def __init__(self, name: _Optional[str] = ..., bindings: _Optional[_Iterable[_Union[InterceptorBinding, _Mapping]]] = ..., failure_policy: _Optional[str] = ..., provider_profiles: _Optional[bool] = ..., expected_audience: _Optional[str] = ..., extension: _Optional[_Union[_extension_pb2.PeerMetadata, _Mapping]] = ...) -> None: ...

class InterceptorBinding(_message.Message):
    __slots__ = ("id", "selector", "phases", "failure_policy")
    ID_FIELD_NUMBER: _ClassVar[int]
    SELECTOR_FIELD_NUMBER: _ClassVar[int]
    PHASES_FIELD_NUMBER: _ClassVar[int]
    FAILURE_POLICY_FIELD_NUMBER: _ClassVar[int]
    id: str
    selector: InterceptorSelector
    phases: _containers.RepeatedScalarFieldContainer[GatewayInterceptorPhase]
    failure_policy: str
    def __init__(self, id: _Optional[str] = ..., selector: _Optional[_Union[InterceptorSelector, _Mapping]] = ..., phases: _Optional[_Iterable[_Union[GatewayInterceptorPhase, str]]] = ..., failure_policy: _Optional[str] = ...) -> None: ...

class InterceptorSelector(_message.Message):
    __slots__ = ("rpc", "service", "method")
    RPC_FIELD_NUMBER: _ClassVar[int]
    SERVICE_FIELD_NUMBER: _ClassVar[int]
    METHOD_FIELD_NUMBER: _ClassVar[int]
    rpc: str
    service: str
    method: str
    def __init__(self, rpc: _Optional[str] = ..., service: _Optional[str] = ..., method: _Optional[str] = ...) -> None: ...

class JsonPatch(_message.Message):
    __slots__ = ("op", "path", "value")
    OP_FIELD_NUMBER: _ClassVar[int]
    PATH_FIELD_NUMBER: _ClassVar[int]
    VALUE_FIELD_NUMBER: _ClassVar[int]
    FROM_FIELD_NUMBER: _ClassVar[int]
    op: str
    path: str
    value: _struct_pb2.Value
    def __init__(self, op: _Optional[str] = ..., path: _Optional[str] = ..., value: _Optional[_Union[_struct_pb2.Value, _Mapping]] = ..., **kwargs) -> None: ...
