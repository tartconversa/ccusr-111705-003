"""只审阅已观察的详情入口，不把候选记录当作已完成的业务。"""

_REASON_LABELS = {
    'address_input_mismatch': '地址输入与观察地址不一致',
    'address_not_recognized': '地址未被服务范围识别',
    'address_changed_after_check': '核对后地址发生变化',
    'no_confirmable_slot': '当前地址无可确认时段',
    'slot_not_selected': '时段未选择',
    'terms_not_confirmed': '上门条款未确认',
    'preview_unavailable': '资格预览未生成',
    'preview_unconfirmed': '页面资格预览为“资格未确认”',
    'preview_address_mismatch': '资格预览指向了其他地址，存在旧状态串扰',
}


def review_entries(entries):
    assessments = []
    for entry in entries:
        detail = entry['detail_fact']
        assessments.append({'service_address': detail['business_key'], 'directory_availability': entry['catalog_fact']['availability'],
                            'provider_seen': detail['provider'], 'qualification': 'unconfirmed', 'slot': None})
    return assessments

def review_eligibility(observations):
    """把资格观察转成客服可引用的摘要：只复述页面结论并附来源，
    unconfirmed 明确给出原因；任何情况下都不输出“可下单”。"""
    summaries = []
    for observation in observations:
        fact = observation['qualification_fact']
        evidence = observation['evidence']
        reason_labels = [_REASON_LABELS.get(reason, reason) for reason in fact['reasons']]
        summaries.append({
            'service': observation['id'],
            'address': observation['address'],
            'provider_seen': evidence.get('provider') or None,
            'qualification': fact['qualification'],
            'reasons': fact['reasons'],
            'reason_labels': reason_labels,
            'slot': evidence.get('slot_selected_text') or None,
            'terms_confirmed': evidence.get('terms_confirmed', False),
            'orderable': False,
            'order_submitted': observation.get('order_submitted', False),
            'observed_at': observation['observed_at'],
            'sources': observation['sources'],
            'reply_guidance': (
                '页面显示资格链齐备，可向客户复述页面预览内容；仍需客户在正式渠道确认，本观察不代表已下单'
                if fact['qualification'] == 'eligible'
                else '资格未确认，不得向客户承诺可预约或可下单，原因：' + ('、'.join(reason_labels) or '未知')
            ),
        })
    return summaries
