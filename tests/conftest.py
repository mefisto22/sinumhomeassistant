"""Valódi HA tesztpéldány, a SINUM vezérlő HTTP API-ja helyett egy hamis routerrel."""
import copy
import re

import pytest

pytest_plugins = ["pytest_homeassistant_custom_component"]

import os as _os
import pytest_homeassistant_custom_component.testing_config.custom_components as _cc  # noqa: E402
_cc.__path__.insert(0, _os.path.join(_os.path.dirname(_os.path.dirname(__file__)), "custom_components"))

BASE = "http://192.168.1.50/api/v1"

COMMON = {"status": "online", "messages": [], "labels": []}

SBUS = [
    {"id": 1, "class": "sbus", "type": "relay", "name": "Relay A", "state": True, "address": 100, "software_version": "SBUS-R v1"},
    {"id": 2, "class": "sbus", "type": "temperature_sensor", "name": "Temp A", "temperature": 215, "address": 101, "software_version": "STT v1"},
    {"id": 3, "class": "sbus", "type": "humidity_sensor", "name": "Hum A", "humidity": 455, "address": 101, "software_version": "STT v1"},
    {"id": 4, "class": "sbus", "type": "light_sensor", "name": "Lux A", "illuminance": 300, "address": 102, "software_version": "LS v1"},
    {"id": 5, "class": "sbus", "type": "motion_sensor", "name": "Motion A", "motion_detected": False, "address": 103, "software_version": "MS v1"},
    {"id": 6, "class": "sbus", "type": "two_state_input_sensor", "name": "Door input", "state": True, "address": 104, "software_version": "IN v1"},
    {"id": 7, "class": "sbus", "type": "rgb_controller", "name": "LED", "state": True, "brightness": 50, "led_color": "#ff0000",
     "white_temperature": 3000, "color_mode": "rgb", "led_strip_type": "rgbww", "address": 105, "software_version": "RGB v1"},
    {"id": 8, "class": "sbus", "type": "blind_controller", "name": "Blind", "current_opening": 40, "target_opening": 40, "labels": ["percent_opening_control"], "address": 106, "software_version": "BL v1"},
    {"id": 9, "class": "sbus", "type": "analog_output", "name": "AO", "value": 2000, "value_minimum": 0, "value_maximum": 10000, "unit": "mV", "address": 107, "software_version": "AO v1"},
    {"id": 10, "class": "sbus", "type": "pulse_width_modulation", "name": "PWM", "duty_cycle": 30, "address": 107, "software_version": "AO v1"},
]
WTP = [
    # same numeric id as an SBUS relay / motion sensor, to probe (class,id) handling
    {"id": 1, "class": "wtp", "type": "relay", "name": "Relay W", "state": False, "address": 200, "software_version": "WTP-R v1"},
    {"id": 5, "class": "wtp", "type": "motion_sensor", "name": "Motion W", "motion_detected": True, "address": 201, "software_version": "WMS v1", "battery": 80},
    {"id": 11, "class": "wtp", "type": "temperature_sensor", "name": "Temp W", "temperature": 199, "address": 202, "software_version": "C-mini v1", "battery": 55},
    {"id": 12, "class": "wtp", "type": "humidity_sensor", "name": "Hum W", "humidity": 500, "address": 203, "software_version": "C-mini v1", "battery": 56},
]
VIRTUAL = [
    {"id": 1, "class": "virtual", "type": "thermostat", "name": "Nappali", "mode": "heating", "state": False,
     "temperature": 0, "humidity": 0, "target_temperature": 215, "target_temperature_minimum": 50, "target_temperature_maximum": 350},
]


def _devices(lst):
    return [{**COMMON, **d} for d in lst]


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    import custom_components
    here = _os.path.join(_os.path.dirname(_os.path.dirname(__file__)), "custom_components")
    if here not in list(custom_components.__path__):
        custom_components.__path__.insert(0, here)
    yield


@pytest.fixture
def api_data():
    return {"sbus": _devices(SBUS), "wtp": _devices(WTP), "virtual": _devices(VIRTUAL)}


class FakeRouter:
    def __init__(self, api_data):
        self.api_data = api_data
        self.state = {"fail": None}
        self.calls = []          # (method, url, json)
        self.routes = []         # (method, regex, fn(url, json) -> (status, payload))

    def add(self, regex, method="POST", callback=None, status=200, payload=None, repeat=True):
        if callback is None:
            fn = lambda url, js: (status, payload)
        else:
            def fn(url, js, _cb=callback):
                r = _cb(url, json=js)
                return (r.status, r.payload) if hasattr(r, "status") else r
        self.routes.insert(0, (method, re.compile(regex) if isinstance(regex, str) else regex, fn))

    def handle(self, method, url, js):
        self.calls.append((method, url, js))
        for m, rx, fn in self.routes:
            if m == method and rx.search(url):
                return fn(url, js)
        mm = re.search(r"/devices/(sbus|wtp|virtual)$", url)
        if method == "GET" and mm:
            f = self.state["fail"]
            if f == "conn":
                import aiohttp
                raise aiohttp.ClientConnectionError("Connection refused")
            if f == "timeout":
                raise TimeoutError()
            if f in ("401", "500"):
                return int(f), {"error": {"message": "x"}}
            return 200, {"data": copy.deepcopy(self.api_data[mm.group(1)])}
        return 404, {"error": {"message": "not found"}}


class _Resp:
    def __init__(self, method, url, status, payload):
        import json as _j
        import aiohttp
        from multidict import CIMultiDict, CIMultiDictProxy
        from yarl import URL
        self.status = status
        self._body = payload if isinstance(payload, bytes) else _j.dumps(payload).encode()
        self.content_type = "application/json"
        self.charset = "utf-8"
        self.request_info = aiohttp.RequestInfo(URL(url), method, CIMultiDictProxy(CIMultiDict()), URL(url))
        self.history = ()
        self.headers = CIMultiDictProxy(CIMultiDict())

    def raise_for_status(self):
        import aiohttp
        if self.status >= 400:
            raise aiohttp.ClientResponseError(self.request_info, self.history, status=self.status, message="err", headers=self.headers)

    async def json(self):
        import json as _j
        return _j.loads(self._body)

    async def read(self):
        return self._body

    async def text(self):
        return self._body.decode()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class _Ctx:
    def __init__(self, router, method, url, js):
        self.router, self.method, self.url, self.js = router, method, url, js

    async def __aenter__(self):
        st, pl = self.router.handle(self.method, self.url, self.js)
        return _Resp(self.method, self.url, st, pl)

    async def __aexit__(self, *a):
        return False


@pytest.fixture
def mock_api(api_data, monkeypatch):
    import aiohttp
    router = FakeRouter(api_data)
    sessions = {"n": 0}

    class FakeSession:
        def __init__(self, *a, **kw):
            sessions["n"] += 1
            self.kw = kw

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        def get(self, url, **kw):
            return _Ctx(router, "GET", str(url), kw.get("json"))

        def post(self, url, **kw):
            return _Ctx(router, "POST", str(url), kw.get("json"))

        def patch(self, url, **kw):
            return _Ctx(router, "PATCH", str(url), kw.get("json"))

        def request(self, method, url, **kw):
            return _Ctx(router, method.upper(), str(url), kw.get("json"))

        async def close(self):
            return None

        closed = False

    monkeypatch.setattr(aiohttp, "ClientSession", FakeSession)
    # Az új kód a HA közös session-jét kéri el; azt is a fake-re cseréljük
    import importlib
    shared = FakeSession()
    for mod in ("custom_components.sinum", "custom_components.sinum.config_flow"):
        try:
            m = importlib.import_module(mod)
        except ImportError:
            continue
        if hasattr(m, "async_get_clientsession"):
            monkeypatch.setattr(m, "async_get_clientsession", lambda hass, *a, **k: shared)
    router.sessions = sessions
    yield router


def count_calls(m, pattern=None):
    return sum(1 for (method, url, js) in m.calls if pattern is None or re.search(pattern, url))
