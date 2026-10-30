"""Bound request bodies before multipart parsing can spool arbitrary uploads."""
from starlette.responses import JSONResponse

class RequestLimit:
    def __init__(self, app): self.app = app
    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope['method'] not in ('POST','PUT','PATCH'):
            return await self.app(scope, receive, send)
        limit = 5*1024*1024+64*1024 if scope['path'] == '/documents' else 16*1024
        size=0; chunks=[]
        while True:
            message=await receive()
            if message['type']=='http.disconnect': return
            size += len(message.get('body',b''))
            if size > limit:
                return await JSONResponse({'detail':'Request body is too large'},status_code=413)(scope, receive, send)
            chunks.append(message)
            if not message.get('more_body',False): break
        async def bounded_receive():
            if chunks: return chunks.pop(0)
            return await receive()
        await self.app(scope,bounded_receive,send)
