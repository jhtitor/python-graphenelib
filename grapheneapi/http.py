import json
import time
import logging
import requests
from .exceptions import (
    RPCError,
    NumRetriesReached
)
from .rpc import Rpc

log = logging.getLogger(__name__)


class Http(Rpc):
    """ RPC Calls
    """
    def rpcexec(self, payload):
        """ Execute a call by sending the payload

            :param json payload: Payload data
            :raises ValueError: if the server does not respond in proper JSON
                                format
            :raises RPCError: if the server returns an error
        """
        log.debug(json.dumps(payload))
        query = requests.post(
            self.url,
            json=payload
        )
        if query.status_code != 200:
            raise

        return query.text
