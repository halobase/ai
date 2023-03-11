from typing import Optional, Any, Mapping, Tuple, Dict, Union

from xooai import Driver as BaseDriver
from xooai import Stream, Executor, PostWrapperAsync, Doc

try:
    from starlette.applications import Starlette
    from starlette.requests import Request
    from starlette.responses import JSONResponse
    from starlette.exceptions import HTTPException
    import uvicorn
    import httpx
except ImportError as e:
    raise ImportError('Please run `pip install xooai[http]` to use the HTTP driver.') from e



class Driver(BaseDriver):

    def __init__(self,
                 *,
                 host: str = '127.0.0.1',
                 port: int = 8080,
                 keyfile: Optional[str] = None,
                 certfile: Optional[str] = None):
        
        self.app = Starlette()
        super().__init__(host=host, 
                         port=port, 
                         keyfile=keyfile, 
                         certfile=certfile)

    def add(self, use: 'Executor', id: Optional[str] = None):

        def post(h: PostWrapperAsync):
            types = h.spec.annotations

            async def call(req: Request):
                kwargs: Mapping[str, Doc] = {}
                json: Mapping[str, Any] = await req.json()

                for k, v in json.items():
                    kwargs[k] = types[k](**v)

                try:
                    res = await h(use, **kwargs)
                except TypeError as e:
                    raise HTTPException(status_code=400, detail=str(e)) from e
                
                return JSONResponse(res.dict())
            
            return call

        if id is None:
            id = use.name

        # add post handlers
        for h in use.post_handlers():
            self.app.add_route(f'/{id}/{h.on}', post(h), methods=['post'])

        # TODO: add stream handlers
        for h in use.stream_handlers():
            pass
    

    def remove(self, id: str):
        pass


    async def post(self, on: str, doc: 'Doc') -> Optional['Doc']:
        
        return await super().post(on, doc)


    async def stream(self, on: str) -> Stream:
        return await super().stream(on)


    def start(self):
        uvicorn.run(app=self.app,
                    host=self.host, 
                    port=self.port,
                    ssl_keyfile=self.keyfile,
                    ssl_certfile=self.certfile)


    def stop(self, timeout: int = 300):
        pass