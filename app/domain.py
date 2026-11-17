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
