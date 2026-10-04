import pytest
from app.workflow import is_valid_transition, roles_for
from app.models import RequestStatus as S
from app.models import Role

def test_workflow_transitions():
    assert is_valid_transition(S.SUBMITTED, S.IN_PROGRESS)
    assert not is_valid_transition(S.SUBMITTED, S.DELIVERED)
    assert not is_valid_transition(S.SUBMITTED, S.ACCEPTED)
    
    assert is_valid_transition(S.IN_PROGRESS, S.DELIVERED)
    assert not is_valid_transition(S.IN_PROGRESS, S.ACCEPTED)
    
    assert is_valid_transition(S.DELIVERED, S.ACCEPTED)
    assert is_valid_transition(S.DELIVERED, S.REJECTED)
    assert not is_valid_transition(S.DELIVERED, S.IN_PROGRESS)
    
    assert is_valid_transition(S.REJECTED, S.IN_PROGRESS)
    assert not is_valid_transition(S.REJECTED, S.SUBMITTED)
    assert not is_valid_transition(S.ACCEPTED, S.IN_PROGRESS)

def test_workflow_roles():
    staff = {Role.OPERATOR, Role.ADMIN}
    client = {Role.CLIENT}
    
    assert roles_for(S.SUBMITTED, S.IN_PROGRESS) == staff
    assert roles_for(S.IN_PROGRESS, S.DELIVERED) == staff
    assert roles_for(S.DELIVERED, S.ACCEPTED) == client
    assert roles_for(S.DELIVERED, S.REJECTED) == client
    assert roles_for(S.REJECTED, S.IN_PROGRESS) == staff
