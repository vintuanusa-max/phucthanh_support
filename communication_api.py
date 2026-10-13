"""Registered by both manager and main bot; ERP provides the admin boundary."""
from fastapi import APIRouter, HTTPException
import communication_policy as policy

router=APIRouter()

@router.get('/communication-config')
def get_communication_config():
    try:
        return policy.public_config(policy.read_raw())
    except Exception:
        raise HTTPException(503, 'Không đọc được config.json trên máy Zalo')

@router.post('/communication-config')
def save_communication_config(payload:dict):
    try:
        return policy.save(payload)
    except policy.PolicyConflict as exc:
        raise HTTPException(409,str(exc))
    except ValueError as exc:
        raise HTTPException(422,str(exc))
    except Exception:
        raise HTTPException(503,'Không lưu được config.json trên máy Zalo')
