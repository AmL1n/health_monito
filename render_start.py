import eventlet
eventlet.monkey_patch()

import os
from server import app, socketio

port = int(os.environ.get("PORT", 10000))
socketio.run(app, host="0.0.0.0", port=port)
