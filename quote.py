"""行情模块: 多数据源容灾(腾讯/新浪/东财)、代码规范化、交易时段判断.

数据源按 SOURCES 中的优先级依次尝试, 第一个成功的即采用; 每个刷新周期
都从头尝试, 因此主源(腾讯)恢复后会自动切回, 无需手动干预.
"""
import logging
import re
from dataclasses import dataclass
from datetime import datetime, time as dtime

import requests

log = logging.getLogger(__name__)

_INPUT_RE = re.compile(r"^(sh|sz|bj)?(\d{6})$", re.IGNORECASE)

# 常见指数别名: 沪市指数代码与深市股票数字冲突, 必须带前缀; 这里额外接受
# 通达信风格的上证指数代码, 方便直接输入。其余指数请用带前缀的标准代码。
_ALIASES = {
    "1A0001": "sh000001",   # 上证指数(通达信代码)
}

# A 股交易时段(北京时间), 含集合竞价
_SESSIONS = ((dtime(9, 15), dtime(11, 30)), (dtime(13, 0), dtime(15, 0)))


class AllSourcesError(Exception):
    """所有行情源均不可用时抛出."""


@dataclass
class Quote:
    code: str          # 带市场前缀, 如 sh600519
    name: str
    price: float       # 最新价
    prev_close: float  # 昨收
    pct: float         # 涨跌幅(%)
    high: float = 0.0  # 当日最高
    low: float = 0.0   # 当日最低


def normalize_code(raw):
    """把用户输入(600519 / sh600519)规范成带市场前缀的代码, 无法识别返回 None."""
    if not isinstance(raw, str):
        return None
    raw = raw.strip()
    if raw.upper() in _ALIASES:     # 指数等别名直达
        return _ALIASES[raw.upper()]
    m = _INPUT_RE.match(raw.lower())
    if not m:
        return None
    prefix, num = m.group(1), m.group(2)
    if prefix:
        return prefix + num
    if num[0] in "569":  # 沪市主板/科创板/沪B(6/9)、沪市基金/ETF/LOF(5)
        return "sh" + num
    if num[0] in "013":  # 深市主板/创业板(0/3)、深市基金/ETF/LOF(1)
        return "sz" + num
    if num[0] in "48":   # 北交所
        return "bj" + num
    return None


def price_decimals(code):
    """该标的报价的小数位数: 沪市 5xxxxx / 深市 1xxxxx 为基金/ETF/LOF, 3 位; 其余股票 2 位."""
    num = code[2:] if code[:2] in ("sh", "sz", "bj") else code
    if num and num[0] in "15":
        return 3
    return 2


def _opt_float(value):
    """可选数值字段: 无法解析(含 None/空/'-')时返回 0.0."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _make_quote(code, name, price, prev_close, pct=None, high=None, low=None):
    """统一构造 Quote, 处理停牌(价 0 用昨收兜底)与涨跌幅缺省计算; 非法返回 None."""
    try:
        price = float(price)
        prev_close = float(prev_close)
    except (TypeError, ValueError):
        return None
    if price <= 0:           # 停牌/竞价前现价可能为 0, 用昨收兜底
        price = prev_close
    if price <= 0:
        return None
    if pct is None:
        pct = (price - prev_close) / prev_close * 100 if prev_close > 0 else 0.0
    else:
        try:
            pct = float(pct)
        except (TypeError, ValueError):
            pct = (price - prev_close) / prev_close * 100 if prev_close > 0 else 0.0
    return Quote(code=code, name=name, price=price, prev_close=prev_close, pct=pct,
                 high=_opt_float(high), low=_opt_float(low))


# ---------------- 数据源 1: 腾讯 ----------------

_TENCENT_URL = "https://qt.gtimg.cn/q="
_TENCENT_HEADERS = {"Referer": "https://gu.qq.com/"}
_TENCENT_LINE_RE = re.compile(r'v_(\w+)="([^"]*)"')
_T_NAME, _T_PRICE, _T_PREV, _T_PCT, _T_MIN = 1, 3, 4, 32, 33
_T_HIGH, _T_LOW = 33, 34


def _fetch_tencent(codes, timeout):
    resp = requests.get(_TENCENT_URL + ",".join(codes),
                        timeout=timeout, headers=_TENCENT_HEADERS)
    resp.raise_for_status()
    resp.encoding = "gbk"
    result = {}
    for code, payload in _TENCENT_LINE_RE.findall(resp.text):
        fields = payload.split("~")
        if len(fields) < _T_MIN:
            continue
        pct = fields[_T_PCT] if len(fields) > _T_PCT else None
        high = fields[_T_HIGH] if len(fields) > _T_HIGH else None
        low = fields[_T_LOW] if len(fields) > _T_LOW else None
        q = _make_quote(code, fields[_T_NAME], fields[_T_PRICE], fields[_T_PREV],
                        pct, high, low)
        if q is not None:
            result[code] = q
    return result


# ---------------- 数据源 2: 新浪 ----------------

_SINA_URL = "https://hq.sinajs.cn/list="
_SINA_HEADERS = {"Referer": "https://finance.sina.com.cn/"}
_SINA_LINE_RE = re.compile(r'hq_str_(\w+)="([^"]*)"')
_S_NAME, _S_PREV, _S_PRICE, _S_MIN = 0, 2, 3, 4
_S_HIGH, _S_LOW = 4, 5


def _fetch_sina(codes, timeout):
    resp = requests.get(_SINA_URL + ",".join(codes),
                        timeout=timeout, headers=_SINA_HEADERS)
    resp.raise_for_status()
    resp.encoding = "gbk"
    result = {}
    for code, payload in _SINA_LINE_RE.findall(resp.text):
        fields = payload.split(",")
        if len(fields) < _S_MIN:
            continue
        # 新浪不直接给涨跌幅, 由 _make_quote 用昨收/现价计算
        high = fields[_S_HIGH] if len(fields) > _S_HIGH else None
        low = fields[_S_LOW] if len(fields) > _S_LOW else None
        q = _make_quote(code, fields[_S_NAME], fields[_S_PRICE], fields[_S_PREV],
                        high=high, low=low)
        if q is not None:
            result[code] = q
    return result


# ---------------- 数据源 3: 东财 ----------------

_EM_URL = "https://push2.eastmoney.com/api/qt/stock/get"
_EM_FIELDS = "f43,f44,f45,f57,f58,f59,f60,f170"  # f44=最高 f45=最低
_EM_PREFIX = {"sh": "1", "sz": "0", "bj": "0"}


def _fetch_eastmoney(codes, timeout):
    """东财批量接口字段不稳定, 故逐只请求(本源仅在腾讯+新浪都失败时触发)."""
    result = {}
    for code in codes:
        prefix = _EM_PREFIX.get(code[:2])
        if prefix is None:
            continue
        secid = f"{prefix}.{code[2:]}"
        resp = requests.get(_EM_URL, timeout=timeout,
                            params={"secid": secid, "fields": _EM_FIELDS})
        resp.raise_for_status()
        data = (resp.json() or {}).get("data")
        if not data:
            continue
        scale = 10 ** int(data.get("f59", 2))   # f59=价格小数位数
        price = _em_num(data.get("f43"), scale)
        prev = _em_num(data.get("f60"), scale)
        high = _em_num(data.get("f44"), scale)
        low = _em_num(data.get("f45"), scale)
        pct = _em_num(data.get("f170"), 100)     # 涨跌幅放大 100 倍
        q = _make_quote(code, data.get("f58", code[2:]), price, prev, pct, high, low)
        if q is not None:
            result[code] = q
    return result


def _em_num(value, scale):
    """东财数值字段还原; '-'/None 视为缺失返回 0."""
    if value in (None, "-", ""):
        return 0.0
    try:
        return float(value) / scale
    except (TypeError, ValueError):
        return 0.0


# ---------------- 容灾调度 ----------------

SOURCES = (
    ("腾讯", _fetch_tencent),
    ("新浪", _fetch_sina),
    ("东财", _fetch_eastmoney),
)


def fetch_quotes(codes, timeout=4.0):
    """按优先级依次尝试各数据源, 第一个返回非空数据的即采用.

    返回 (quotes_dict, source_name); 若所有源都失败/空, 抛 AllSourcesError.
    """
    if not codes:
        return {}, None
    errors = []
    for name, fetch in SOURCES:
        try:
            quotes = fetch(codes, timeout)
        except requests.RequestException as e:
            errors.append(f"{name}({e.__class__.__name__})")
            continue
        except (ValueError, KeyError) as e:  # JSON/字段解析异常, 降级到下一个源
            errors.append(f"{name}(parse:{e})")
            continue
        if quotes:
            return quotes, name
        errors.append(f"{name}(空)")
    raise AllSourcesError("所有行情源均不可用: " + ", ".join(errors))


def is_trading_time(now=None) -> bool:
    """是否处于 A 股交易时段(工作日 9:15-11:30 / 13:00-15:00)."""
    now = now or datetime.now()
    if now.weekday() >= 5:
        return False
    t = now.time()
    return any(start <= t <= end for start, end in _SESSIONS)
