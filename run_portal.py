#!/usr/bin/env python

from portal import app
from portal import log_api

if __name__ == "__main__":
    logger = log_api.init_logger()
    app.run(host='localhost', ssl_context=('./ssl/server.crt', './ssl/server.key'))
