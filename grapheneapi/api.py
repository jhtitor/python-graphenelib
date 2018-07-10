import logging
from .websocket import Websocket
from .http import Http
from collections import Counter
from itertools import cycle
from .exceptions import (
    RPCError,
    NumRetriesReached
)
log = logging.getLogger(__name__)


class Api:
    def __init__(self, urls, user="", password="", **kwargs):

        self._connections = dict()
        self._url_counter = Counter()
        self._kwargs = kwargs
        self.user = user
        self.password = password
        self.num_retries = kwargs.pop("num_retries", 0)

        if not isinstance(urls, list):
            urls = [urls]

        for url in urls:
            self._url_counter[url] = 0

        self.url = urls[0]
        self._active_url = None
        self.connect()

    @property
    def api_id(self):
        return self.connection.api_id

    @property
    def connection(self):
        if self._active_url != self.url:
            if self.url[:2] == "ws":
                self._active_connection = Websocket(self.url, **self._kwargs)
            elif self.url[:4] == "http":
                self._active_connection = Http(self.url, **self._kwargs)
        return self._active_connection

    def connect(self):
        try:
            self.connection.connect()
        except Exception as e:
            log.warning(str(e))
            self.error_url()
            self.next()
        self._active_url = self.url
        self.register_apis()

    def register_apis(self):
        pass

    def find_next(self):
        """ Find the next url in the list
        """
        urls = [
            k
            for k, v in self._url_counter.items()
            if (int(self.num_retries) >= 0 and
                v <= self.num_retries and
                (k != self.url or len(self._url_counter) == 1))
        ]
        if not len(urls):
            raise NumRetriesReached
        url = urls[0]
        return url

    def reset_counter(self):
        """ reset the failed connection counters
        """
        for i in self._url_counter:
            self._url_counter[i] = 0

    def error_url(self):
        if self.url:
            self._url_counter[self.url] += 1

    def next(self):
        self.connection.disconnect()
        self.url = self.find_next()
        self.connect()

    def post_process_exception(self, exception):
        raise exception

    def __getattr__(self, name):
        def func(*args, **kwargs):
            while True:
                func = self.connection.__getattr__(name)
                try:
                    r = func(*args, **kwargs)
                    self.reset_counter()
                    break
                except KeyboardInterrupt:
                    raise
                except ValueError:
                    raise
                except RPCError as e:
                    self.post_process_exception(e)
                    break
                except Exception as e:
                    log.warning(str(e))
                    self.error_url()
                    self.next()

            return r
        return func
