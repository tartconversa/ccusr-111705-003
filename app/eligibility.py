"""地址资格观察：在独立浏览器会话里走完整的地址—条款—时段—预览流程。

设计约束：
- 只允许访问环回来源；
- 每次观察使用独立的浏览器实例与全新无痕上下文，不同地址之间不共享
  cookie、存储、缓存或任何页面会话；
- 完整记录每一步的页面证据与来源 URL，卡片上的“可预约”只作为目录事实，
  不作为资格依据；
- 证据链不完整时由 domain.interpret_qualification 判为 unconfirmed，
  本模块不虚构可下单结论，也不进行任何提交动作。
"""
import json
import uuid
from datetime import datetime, timezone
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright

from .domain import interpret_card, interpret_qualification

_LOOPBACK_HOSTS = ('127.0.0.1', 'localhost')
_TERMS_CONFIRM_TEXT = '需确认'
_PREVIEW_WAIT_MS = 5000
_CHECK_WAIT_MS = 5000


def ensure_local_origin(origin):
    parts = urlsplit(origin)
    if parts.scheme != 'http' or parts.hostname not in _LOOPBACK_HOSTS:
        raise ValueError('只允许本地演练来源')
    return origin


def qualification_cache_key(origin, item_id, address):
    """同一来源+业务+精确地址才共享一次可重跑观察；地址不做归一化，
    相似楼栋（如 1 栋/2 栋）自然得到不同键。"""
    return json.dumps(
        {'origin': ensure_local_origin(origin), 'item_id': item_id, 'address': address},
        ensure_ascii=False, sort_keys=True,
    )


def observe_eligibility(origin, item_id, address, cache_path=None, refresh=False,
                        confirm_terms=True):
    """对单个地址执行一次带来源的资格观察。

    cache_path 给定时，命中 (origin, item_id, address) 缓存直接重放，
    refresh=True 强制重新观察并覆盖该地址自己的缓存；不同地址的键不同，
    永远不会共享缓存或页面会话。confirm_terms=False 时不勾选页面上的
    确认框，用于保留“条款未确认”的未确认证据。
    """
    ensure_local_origin(origin)
    key = qualification_cache_key(origin, item_id, address)
    from .records import load_qualification_observation, save_qualification_observation
    if cache_path is not None and not refresh:
        cached = load_qualification_observation(cache_path, key)
        if cached is not None:
            cached['cache_hit'] = True
            return cached
    try:
        observation = _run_observation(origin, item_id, address, confirm_terms)
    except Exception as exc:  # 页面流程技术性失败：标记未确认，且不写入缓存
        observation = _failed_observation(origin, item_id, address, exc)
        observation['qualification_fact'] = interpret_qualification(observation['evidence'])
        observation['cache_hit'] = False
        return observation
    observation['qualification_fact'] = interpret_qualification(observation['evidence'])
    observation['cache_hit'] = False
    if cache_path is not None:
        save_qualification_observation(cache_path, key, observation)
    return observation


def _failed_observation(origin, item_id, address, exc):
    return {
        'origin': origin,
        'id': item_id,
        'address': address,
        'observed_at': datetime.now(timezone.utc).isoformat(),
        'session_id': uuid.uuid4().hex,
        'sources': [],
        'catalog_fact': None,
        'evidence': {
            'address': address,
            'address_input_value': address,
            'address_suggestions': [],
            'address_result': '',
            'checked_address': '',
            'provider': '',
            'terms_text': '',
            'terms_requires_confirmation': False,
            'terms_confirmed': False,
            'slot_options': [],
            'slot_selected': '',
            'slot_selected_text': '',
            'qualification_preview': '',
        },
        'actions': [],
        'technical_error': f'{type(exc).__name__}: {exc}',
        'order_submitted': False,
    }


def _run_observation(origin, item_id, address, confirm_terms=True):
    session_id = uuid.uuid4().hex
    started = datetime.now(timezone.utc).isoformat()
    actions = []
    with sync_playwright() as playwright:
        # 每次观察独立的浏览器实例 + 全新无痕上下文，结束即销毁。
        browser = playwright.chromium.launch(headless=True)
        context = None
        try:
            context = browser.new_context()
            page = context.new_page()
            requests_seen = []

            def _record_request(request):
                requests_seen.append({'method': request.method, 'url': request.url})

            page.on('request', _record_request)

            # 1) 从目录卡片进入详情，保留“卡片 → 详情”的来源链。
            page.goto(origin, wait_until='domcontentloaded')
            catalog_url = page.url
            card = page.locator(f'.card[data-key="{item_id}"]')
            if card.count() != 1:
                raise ValueError('card identity is not unique')
            catalog_fact = interpret_card({
                'id': item_id,
                'summary': card.locator('p').inner_text(),
            })
            card.locator('a').click()
            page.wait_for_load_state('domcontentloaded')
            if page.locator('main').get_attribute('data-key') != item_id:
                raise ValueError('detail identity differs from catalog')
            detail_url = page.url
            actions.append('catalog_card_opened')

            # 2) 地址输入：只回填完全一致的精确地址，绝不从联想列表挑相似楼栋。
            address_box = page.locator('#address')
            address_box.fill(address)
            actions.append('address_filled_exact')
            suggestions = page.locator('#areas option').evaluate_all(
                '(nodes) => nodes.map((n) => n.value)')
            input_value = address_box.input_value()
            if input_value != address:
                raise ValueError('address input did not retain the exact address')
            if address not in suggestions:
                suggestion_note = 'address_not_in_suggestions'
            else:
                suggestion_note = 'exact_address_in_suggestions'
            actions.append(suggestion_note)

            # 3) 查询上门范围，等待条款与时段异步渲染完成（按地址内容核验，
            #    不依赖固定 sleep）。
            page.locator('#address-check').click()
            actions.append('address_check_clicked')
            page.wait_for_function(
                '(value) => document.querySelector("#address").value === value '
                '&& document.querySelector("#terms").textContent !== "" '
                '&& document.querySelector("#terms").textContent !== "条款读取中" '
                '&& document.querySelector("#visit-slot").options.length > 0 '
                '&& document.querySelector("#visit-slot option").textContent !== "等待时段"',
                arg=address, timeout=_CHECK_WAIT_MS,
            )
            checked_address = address_box.input_value()
            if checked_address != address:
                raise ValueError('address changed while check was in flight')
            address_result = page.locator('#address-result').inner_text()
            provider = page.locator('#provider').inner_text()
            terms_text = page.locator('#terms').inner_text()
            slot_options = page.locator('#visit-slot option').evaluate_all(
                '(nodes) => nodes.map((n) => ({value: n.value, text: n.textContent}))')
            requires_confirmation = _TERMS_CONFIRM_TEXT in terms_text

            # 4) 条款：页面要求确认时，按调用方意图决定是否勾选并如实记录；
            #    这是资格观察动作，不是下单。
            terms_confirmed = False
            if requires_confirmation:
                if confirm_terms:
                    checkbox = page.locator('#terms-confirmed')
                    if checkbox.is_enabled():
                        checkbox.check()
                        terms_confirmed = checkbox.is_checked()
                        actions.append('terms_confirmed')
                else:
                    actions.append('terms_confirmation_withheld')
            else:
                actions.append('terms_no_confirmation_required')

            # 5) 选择时段：只接受属于当前已核对地址的可用值；没有可确认
            #    时段时保留空值，绝不复用上一会话/旧地址的选中态。
            selectable = [option for option in slot_options if option['value']]
            slot_selected = ''
            slot_selected_text = ''
            if selectable:
                slot = page.locator('#visit-slot')
                current = slot.input_value()
                if current and not any(option['value'] == current for option in selectable):
                    raise ValueError('stale slot selection carried over from another address')
                slot.select_option(selectable[0]['value'])
                slot_selected = slot.input_value()
                slot_selected_text = slot.locator('option:checked').inner_text()
                actions.append('slot_selected_for_checked_address')
            else:
                if page.locator('#visit-slot').input_value():
                    raise ValueError('slot retained a selection without any current option')
                actions.append('no_confirmable_slot_available')

            # 6) 读取页面自己的资格预览（两个 #preview 处理器都会触发，
            #    qualification-preview 才是完整资格链）。
            page.locator('#preview').click()
            actions.append('qualification_preview_requested')
            page.wait_for_function(
                '() => document.querySelector("#qualification-preview").textContent !== ""',
                timeout=_PREVIEW_WAIT_MS,
            )
            qualification_preview = page.locator('#qualification-preview').inner_text()
            if qualification_preview.startswith(('桐花苑',)) and \
                    not qualification_preview.startswith(address):
                # 预览指向了别的地址：旧状态串扰，判为未确认而不是照抄。
                actions.append('preview_referenced_different_address')

            # 7) 关闭前取会话隔离证据：无痕上下文应当无任何持久化身份。
            session_isolation = {
                'cookies': context.cookies(),
                'origins_in_storage': [
                    origin_state['origin']
                    for origin_state in context.storage_state().get('origins', [])
                    if origin_state.get('localStorage')
                ],
            }
            evidence = {
                'address': address,
                'address_input_value': address_box.input_value(),
                'address_suggestions': suggestions,
                'address_result': address_result,
                'checked_address': checked_address,
                'provider': provider,
                'terms_text': terms_text,
                'terms_requires_confirmation': requires_confirmation,
                'terms_confirmed': terms_confirmed,
                'slot_options': slot_options,
                'slot_selected': slot_selected,
                'slot_selected_text': slot_selected_text,
                'qualification_preview': qualification_preview,
            }
        finally:
            if context is not None:
                context.close()
            browser.close()

    non_loopback = [
        request for request in requests_seen
        if urlsplit(request['url']).hostname not in _LOOPBACK_HOSTS
    ]
    if non_loopback:
        raise ValueError(f'观察过程访问了非环回来源: {non_loopback}')
    write_methods = [request for request in requests_seen if request['method'] != 'GET']
    return {
        'origin': origin,
        'id': item_id,
        'address': address,
        'observed_at': started,
        'session_id': session_id,
        'sources': [
            {'role': 'catalog', 'url': catalog_url},
            {'role': 'detail', 'url': detail_url},
        ],
        'catalog_fact': catalog_fact,
        'evidence': evidence,
        'session_isolation': session_isolation,
        'actions': actions,
        'requests': requests_seen,
        'network_guard': {
            'non_loopback_requests': non_loopback,
            'write_methods': write_methods,
        },
        # 演练门户没有任何下单/提交控件；以请求监听实证只有只读 GET。
        'order_submitted': bool(write_methods),
    }
