"""Candidate review of observed entry facts, never a completed transaction."""

def review_entries(entries):
    assessments = []
    for entry in entries:
        detail = entry['detail_fact']
        assessments.append({'service_address': detail['business_key'], 'directory_availability': entry['catalog_fact']['availability'],
                            'provider_seen': detail['provider'], 'qualification': 'unconfirmed', 'slot': None})
    return assessments
