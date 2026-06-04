"""TickView 入口: 组装配置/行情/界面, 启动主循环."""
import logging
import logging.handlers
import queue
import threading

import config
import quote
from ui import TickViewApp

log = logging.getLogger(__name__)

REFRESH_TRADING = 3   # 交易时段刷新间隔(秒)
REFRESH_IDLE = 60     # 非交易时段刷新间隔(秒)


def setup_logging():
    log_dir = config.config_dir()
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(
            log_dir / "tickview.log", maxBytes=512 * 1024,
            backupCount=1, encoding="utf-8")
    except OSError:
        handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)


class QuoteWorker(threading.Thread):
    """后台行情线程: 按交易时段调整频率, 结果经 queue 送回 UI 线程."""

    def __init__(self, get_codes, out_queue):
        super().__init__(daemon=True, name="quote-worker")
        self._get_codes = get_codes
        self._queue = out_queue
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._fetch_ok = True       # 仅在成功/失败状态切换时记日志, 避免刷屏
        self._last_source = None    # 上次生效的行情源, 用于检测源切换

    def poke(self):
        """配置变更后立即触发一次拉取."""
        self._wake.set()

    def stop(self):
        self._stop.set()
        self._wake.set()

    def run(self):
        while not self._stop.is_set():
            codes = self._get_codes()
            if codes:
                try:
                    quotes, source = quote.fetch_quotes(codes)
                    self._queue.put(("quotes", quotes))
                    if not self._fetch_ok:
                        log.info("行情拉取已恢复, 当前源: %s", source)
                    elif source != self._last_source:
                        log.info("行情源切换为: %s", source)
                    self._fetch_ok = True
                    self._last_source = source
                except quote.AllSourcesError as e:
                    self._queue.put(("error", str(e)))
                    if self._fetch_ok:
                        log.warning("所有行情源均失败, 静默重试中: %s", e)
                        self._fetch_ok = False
            interval = REFRESH_TRADING if quote.is_trading_time() else REFRESH_IDLE
            self._wake.wait(timeout=interval)
            self._wake.clear()


def main():
    setup_logging()
    log.info("TickView 启动")
    cfg = config.load()
    out_queue = queue.Queue()
    app = TickViewApp(cfg, out_queue)
    worker = QuoteWorker(get_codes=app.subscribed_codes, out_queue=out_queue)
    app.on_config_changed = worker.poke
    worker.start()
    try:
        app.run()
    finally:
        worker.stop()
        log.info("TickView 退出")


if __name__ == "__main__":
    main()
