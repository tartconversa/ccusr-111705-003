"""只审阅已观察的详情入口，不把候选记录当作已完成的业务。"""

def review_entries(entries):
    assessments = []
    for entry in entries:
        detail = entry['detail_fact']
        assessments.append({'service_address': detail['business_key'], 'directory_availability': entry['catalog_fact']['availability'],
                            'provider_seen': detail['provider'], 'qualification': 'unconfirmed', 'slot': None})
    return assessments
