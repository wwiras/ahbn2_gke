"""Observational K7 feasibility tracing for DC-SoC maintenance RPCs."""
from __future__ import annotations

REQUEST_ID_METADATA_KEY = "x-k7-request-id"


def _request_id(context) -> str:
    if context is None or not hasattr(context, "invocation_metadata"):
        return ""
    return next((item.value for item in context.invocation_metadata()
                 if item.key == REQUEST_ID_METADATA_KEY), "")


def _phase(request) -> str:
    if request.explicit_du:
        return "explicit_du"
    return "rejoin" if request.available else "leave"


def apply_with_trace(service, request, context, original_handler, *, log_event, now):
    """Call the canonical handler unless dedicated K7 trace metadata is present."""
    request_id = _request_id(context)
    if not request_id:
        return original_handler(request, context)

    maintenance = service.state.dcsoc_maintenance
    base = {
        "request_id": request_id,
        "phase": _phase(request),
        "action": _phase(request),
        "affected_peer": int(request.node_id),
        "receiving_peer": service.state.peer_id,
    }

    log_event(event="k7_dcsoc_rpc_handler_entry", handler_entry_time=now(), **base)
    if maintenance is None:
        log_event(event="k7_dcsoc_rpc_handler_exit", handler_exit_time=now(),
                  success=False, sync_peer_executed=False,
                  error="not a DC-SoC peer", **base)
        return service.state._k7_peer_pb2.Ack(ok=False, message="not a DC-SoC peer")

    sync_peer_executed = False
    try:
        log_event(event="k7_dcsoc_rpc_before_set_availability",
                  before_set_availability_time=now(),
                  operation="explicit_du" if request.explicit_du else "set_availability", **base)
        if request.explicit_du:
            maintenance.explicit_du(reason=request.reason or "explicit_du")
            changed = True
        else:
            changed = maintenance.set_availability(
                int(request.node_id), bool(request.available),
                reason=request.reason or "availability",
            )
        log_event(event="k7_dcsoc_rpc_after_set_availability",
                  after_set_availability_time=now(), changed=bool(changed), **base)
        log_event(event="k7_dcsoc_rpc_before_sync_peer",
                  before_sync_peer_time=now(), sync_peer_executed=True, **base)
        sync_peer_executed = True
        maintenance.sync_peer(service.state)
        log_event(event="k7_dcsoc_rpc_after_sync_peer",
                  after_sync_peer_time=now(), sync_peer_executed=True, **base)
        if maintenance.events and changed:
            log_event(
                event="dcsoc_maintenance", run_id=service.state.run_id,
                experiment=service.state.experiment, peer_id=service.state.peer_id,
                **maintenance.events[-1],
                core_replacement_count=maintenance.core_replacement_count,
                recluster_count=maintenance.recluster_count,
                rejoin_assignment_count=maintenance.rejoin_assignment_count,
            )
        reply = service.state._k7_peer_pb2.Ack(
            ok=True, message="maintenance applied" if changed else "no transition")
        log_event(event="k7_dcsoc_rpc_handler_exit", handler_exit_time=now(),
                  success=True, sync_peer_executed=True, **base)
        return reply
    except Exception as error:
        log_event(event="k7_dcsoc_rpc_handler_exit", handler_exit_time=now(),
                  success=False, sync_peer_executed=sync_peer_executed,
                  error=repr(error), **base)
        raise


def install(peer_module) -> None:
    """Install tracing only in the K7 runtime; canonical peer.py stays untouched."""
    original_handler = peer_module.PeerService.ApplyDCSOCMaintenance
    peer_module.PeerState._k7_peer_pb2 = peer_module.peer_pb2

    def traced_handler(self, request, context):
        return apply_with_trace(
            self, request, context,
            lambda req, ctx: original_handler(self, req, ctx),
            log_event=peer_module.log_event, now=peer_module.now,
        )

    peer_module.PeerService.ApplyDCSOCMaintenance = traced_handler
