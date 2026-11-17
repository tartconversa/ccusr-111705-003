"""公开目录采集与地址资格观察演示。"""
import json
import sys

from .capture import read_catalog
from .eligibility import observe_eligibility
from .review import review_eligibility


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print(json.dumps(read_catalog('http://127.0.0.1:8765/'), ensure_ascii=False, indent=2))
        return
    if argv[0] != 'observe' or len(argv) < 3:
        print('用法: python -m app.cli observe <item_id> <地址> [--origin URL] [--cache PATH] [--refresh]')
        raise SystemExit(2)
    item_id, address = argv[1], argv[2]
    origin = 'http://127.0.0.1:8765/'
    cache_path = None
    refresh = False
    rest = argv[3:]
    while rest:
        flag = rest.pop(0)
        if flag == '--origin':
            origin = rest.pop(0)
        elif flag == '--cache':
            cache_path = rest.pop(0)
        elif flag == '--refresh':
            refresh = True
        else:
            raise SystemExit(f'未知参数: {flag}')
    observation = observe_eligibility(origin, item_id, address,
                                      cache_path=cache_path, refresh=refresh)
    print(json.dumps(review_eligibility([observation])[0], ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
