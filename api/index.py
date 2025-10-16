from server import app

def handler(request, context):
    """Vercel serverless function handler."""
    return app(request, context)