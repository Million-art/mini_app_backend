from webhook import handler  # Import the handler class from webhook.py
from wsgiref.simple_server import make_server

# WSGI application entry point
def application(environ, start_response):
    # Create an HTTP request handler
    handler_obj = handler(environ, start_response)
    if environ['REQUEST_METHOD'] == 'POST':
        handler_obj.do_POST()
    else:
        handler_obj.do_GET()
    return []
