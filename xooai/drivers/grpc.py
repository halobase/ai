from typing import Optional

from xooai import Driver as BaseDriver
from xooai import Stream, DocArray

try:
    import grpcio
except ImportError as e:
    raise ImportError('Please run `pip install xooai[grpc]` to use the gRPC driver.') from e


class Driver(BaseDriver):

    async def post(self, on: str, docs: Optional[DocArray]) -> Optional[DocArray]:
        return await super().post(on, docs)
    
    async def stream(self, on: str) -> Stream:
        return await super().stream(on)
    
    async def start(self):
        return await super().start()
    
    async def stop(self, timeout: int = 300):
        return await super().stop(timeout)