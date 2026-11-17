"""上门服务的地址资格与可约时段核验：目录卡片既有数据约定。"""
import re

def interpret_card(item):
    parts = item['summary'].split(' · ', 1)
    if len(parts) != 2:
        raise ValueError('卡片摘要格式无效')
    condition, observation = parts
    found = re.fullmatch(r"(?P<amount>可预约)", observation)
    if not found:
        raise ValueError('卡片状态未识别')
    amount = found.group('amount')
    return {'kind': 'service', 'identity': item['id'], 'condition': condition, 'availability': observation, 'eligible': int(amount) if amount.isdigit() else amount}

def interpret_entry(catalog_fact, signal):
    if signal['service'] != catalog_fact['identity']:
        raise ValueError('service item mismatch')
    return {'business_key': f"{signal['service']}:{signal['address'] or 'address-pending'}", 'address': signal['address'], 'provider': signal['provider'], 'qualification': 'unconfirmed' if not signal['address'] else 'address-entered'}

def interpret_qualification(evidence):
    """把页面上观察到的证据判读为资格结论。

    证据链任一环节缺失（地址未识别、无可确认时段、条款未确认、预览与当前
    地址不一致等）都返回 unconfirmed 并给出原因；这里只复述页面自己的资格
    预览，永远不推断“可下单”。
    """
    reasons = []
    address = evidence['address']
    if evidence.get('address_input_value') != address:
        reasons.append('address_input_mismatch')
    address_result = evidence.get('address_result') or ''
    if not address_result or address_result == '地址未确认' or not address_result.startswith(address):
        reasons.append('address_not_recognized')
    if evidence.get('checked_address') != address:
        reasons.append('address_changed_after_check')
    selectable = [option for option in evidence.get('slot_options', []) if option.get('value')]
    if not selectable:
        reasons.append('no_confirmable_slot')
    elif not evidence.get('slot_selected'):
        reasons.append('slot_not_selected')
    if evidence.get('terms_requires_confirmation') and not evidence.get('terms_confirmed'):
        reasons.append('terms_not_confirmed')
    preview = evidence.get('qualification_preview') or ''
    if not preview:
        reasons.append('preview_unavailable')
    elif preview == '资格未确认':
        reasons.append('preview_unconfirmed')
    elif not preview.startswith(address):
        reasons.append('preview_address_mismatch')
    return {'qualification': 'eligible' if not reasons else 'unconfirmed',
            'reasons': reasons,
            'orderable': False,
            'note': '仅为页面资格观察，不构成可下单结论，未提交任何订单'}
