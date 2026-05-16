from conduit.shared.models import (
    IssueCode, KBEntry, Request, ChildSubRequest, NoDispatchResolution,
    NDProvenanceKB, NDProvenanceField, Event,
    EventRequestCreated, EventChildTriaged, EventChildAnswered,
    EventChildDeferred, EventChildParked, EventChildClosed, EventChildReopened,
)

def test_models_registered():
    assert IssueCode.__tablename__ == "issue_code"
    assert KBEntry.__tablename__ == "kb_entry"
    assert Request.__tablename__ == "request"
    assert ChildSubRequest.__tablename__ == "child_sub_request"
    assert NoDispatchResolution.__tablename__ == "no_dispatch_resolution"
    assert NDProvenanceKB.__tablename__ == "nd_provenance_kb"
    assert NDProvenanceField.__tablename__ == "nd_provenance_field"
    assert EventChildAnswered.__tablename__ == "event_child_answered"
