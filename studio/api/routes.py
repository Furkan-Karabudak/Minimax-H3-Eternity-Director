import logging

log = logging.getLogger(__name__)

def init_studio_routes():
    """Register Studio HTTP and WebSocket endpoints on ComfyUI's PromptServer."""
    try:
        from aiohttp import web
        from server import PromptServer
    except ImportError:
        log.debug("ComfyUI server / aiohttp not available; skipping route registration.")
        return
    server_instance = getattr(PromptServer, "instance", None)
    if server_instance is None or not hasattr(server_instance, "routes"):
        log.warning("PromptServer instance not ready; studio routes will not be mounted.")
        return

    # Modern namespaced studio endpoints: /eternity_studio/*
    @server_instance.routes.get("/eternity_studio/status")
    async def get_studio_status(request):
        return web.json_response({
            "status": "online",
            "version": "0.1.0-studio.alpha",
            "suite": "Eternity Studio"
        })
