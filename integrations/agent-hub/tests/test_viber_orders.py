import ast
from pathlib import Path
from types import SimpleNamespace
import re
from hub.order_policy import sanitize,eligible


def policy():
    return sanitize({'viber_allowed_thread_ids':['viber:g1'],
                     'viber_contact_rules':[{'name':'CDG','receive_messages':True,'auto_order':True}],
                     'viber_internal_members':['Nhân viên']})


def test_viber_orders_require_allowlist_customer_and_explicit_policy():
    message=dict(thread_id='viber:g1',display_name='CDG',sender='Dung Trần',direction='incoming',origin='customer')
    assert eligible(policy(),'viber',message)
    assert not eligible(sanitize({}),'viber',message)
    for change in [dict(thread_id='viber:g2'),dict(origin='staff'),dict(direction='outgoing'),
                   dict(sender='Nhân viên'),dict(revision=True),dict(recalled=True)]:
        assert not eligible(policy(),'viber',{**message,**change})


def test_staged_erp_accepts_only_bound_cdg_viber():
    tree=ast.parse((Path(__file__).resolve().parents[1]/'deploy/erp/zalo_router.py').read_text(encoding='utf-8'))
    guard=next(n.test for n in ast.walk(tree) if isinstance(n,ast.If)
               and 'Viber requires the verified CDG' in ast.unparse(n))
    # Select the inserted guard itself, not its containing function's other ifs.
    expr=compile(ast.Expression(guard),'<guard>','eval')
    def blocked(**changes):
        req=SimpleNamespace(source='viber',customer_id='customer',group_id='viber:g1',source_account='viber-personal-1')
        for k,v in changes.items():setattr(req,k,v)
        return eval(expr,{'req':req})
    assert not blocked()
    assert blocked(customer_id=None)
    assert blocked(group_id='viber:g2')
    assert blocked(source_account='other')
    assert not blocked(source='zalo')
    assignment=next(n for n in ast.walk(tree) if isinstance(n,ast.Assign)
                    and any(isinstance(t,ast.Name) and t.id=='identity_pattern' for t in n.targets))
    for source,valid,invalid in [('viber','viber:g1','viber:g2'),('zalo','g123','viber:g1'),('whatsapp','123@g.us','g123')]:
        pattern=eval(compile(ast.Expression(assignment.value),'<pattern>','eval'),{'req':SimpleNamespace(source=source)})
        assert re.fullmatch(pattern,valid) and not re.fullmatch(pattern,invalid)
