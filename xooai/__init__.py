__version__ = '0.0.0'

from typing import (
    TypeVar, 
    ForwardRef, 
    Optional,
    Union,
    Tuple,
    Dict,
    Any,
    Iterable, 
    Callable,
    TYPE_CHECKING,
)
from dataclasses import dataclass
from abc import ABC, abstractmethod
from urllib.parse import urlparse

from pydantic import BaseModel
from pydantic.dataclasses import dataclass as doc


if TYPE_CHECKING:
    from PIL.Image import Image as PILImage


Tensor = TypeVar('Tensor', bound=ForwardRef('numpy.ndarray'))


class Driver(ABC):

    def __init__(self, gateway: Optional[str] = None):
        ''''Create a driver instance.
        
        'gateway' specifies a gateway address to invoke endpoints from remote
        executors. The default gateway directs to localhost:8080.
        '''
        self.gateway = gateway or 'localhost:8080'

    
    @abstractmethod
    def add(self, use: 'Executor', id: Optional[str] = None):
        '''Adds an executor into the driver to subscribe on docarray request.
        
        'id' should default to the executor's name if not specified. NOTE that
        this method should inspect all methods decorated by 'post' or 'stream'
        in the executor being added and then remember the type of the arguments
        of these methods so we can instantiate them by reflection when receiving
        a request.
        '''
        raise NotImplementedError


    @abstractmethod
    def remove(self, id: str):
        '''Removes an executor specified by 'id' from the driver.'''
        raise NotImplementedError


    @abstractmethod
    async def post(self, on: str, docs: Optional['DocArray']) -> Optional['DocArray']:
        '''Posts a docarray to the endpoint speicified by 'on'.'''
        raise NotImplementedError


    @abstractmethod
    async def stream(self, on: str) -> 'Stream':
        '''Creates a stream used to send/receive docarray to/from an endpoint'''
        raise NotImplementedError


    @abstractmethod
    async def start(self):
        '''Starts up the driver but non-blocking to receive docarray request'''
        raise NotImplementedError


    @abstractmethod
    async def stop(self, timeout: int = 300):
        '''Stops the driver in 'timeout' milliseconds, default to 300ms.'''
        raise NotImplementedError
    


class NoopDriver(Driver):

    async def post(self, on: str, docs: Optional['DocArray']) -> Optional['DocArray']:
        return await super().post(on, docs)
    
    async def stream(self, on: str) -> 'Stream':
        return await super().stream(on)
    
    async def start(self):
        return await super().start()
    
    async def stop(self, timeout: int = 300):
        return await super().stop(timeout)



class Doc(BaseModel):
    '''A class with some abstract methods to represent model input or output.'''

    id: Optional[str]
    ref: Optional[str]
    value: Optional[bytes]


    @abstractmethod
    def tensor(self) -> Tensor:
        '''Returns a tensor representation of the doc.'''
        raise NotImplementedError



class DocArray(BaseModel):
    '''A class representing a series of docs.'''
    docs: Optional[Iterable[Doc]]


    def __iter__(self):
        yield from self.docs



class Text(Doc):
    '''A class derived from Doc for representing text.'''
    text: Optional[str]

    def tensor(self) -> Tensor:
        # TODO:
        raise NotImplementedError
        


class Image(Doc):
    '''A class derived from Doc for representing an image.'''
    image: Optional["PILImage"]


    def tensor(self) -> Tensor:
        # TODO: 
        raise NotImplementedError
    

    def encode(self) -> bytes:
        # TODO:
        raise NotImplementedError


    def show(self) -> None:
        # TODO:
        raise NotImplementedError



def post(func: Optional[Callable[['Executor', 'DocArray'], Optional['DocArray']]] = None, 
         batch_size: Optional[int] = None,
         timeout: Optional[int] = None,
         on: Optional[str] = None):
    '''Returns a executor's method as a post endpoint handler.

    Using this function as a decorator is recommanded.
    
    Example:
    >>> from typing import Optional
    >>> from xooai import Executor
    >>>
    >>> class MyExecutor(Executor):
    >>>     @post
    >>>     def echo(self, docs: DocArray) -> Optional[DocArray]:
    >>>         return docs
    '''

    def wrap(func):
        # TODO: maintain state
        def __call__(self: 'Executor', docs: 'DocArray') -> Optional[DocArray]:
            # TODO: batching if batch_size > 1
            return func(self, docs)
        return __call__
    
    if func is None:
        # we are being used as @on()
        return wrap
    
    # we are being used as @on
    return wrap(func)


def stream(func: Optional[Callable[['Executor', 'Stream'], None]]):
    '''Returns a Executor method as a stream handler.
    '''
    def wrap(func):
        def __call__(self: 'Executor', stream: 'Stream') -> None:
            return func(self, stream)
        
        return __call__
    
    if func is None:
        # we are being used as @on()
        return wrap
    
    # we are being used as @on
    return wrap(func)


class Stream: ...

class Executor:

    def __init__(self,
                 *,
                 name: Optional[str] = None,
                 driver: Optional['Driver'] = None,
                 post_endpoints: Optional[Iterable[str]] = None,
                 stream_endpoints: Optional[Iterable[str]] = None,):
        '''Instantiate an executor.
        'post_endpoints'
        '''
        self.name = name
        self.driver = driver

        if self.driver is None:
            self.driver = NoopDriver()

        # Inject endpoints dynamically so that they can be accessed by self.post
        # using getattr.
        if post_endpoints:
            for ep in post_endpoints:
                setattr(self, ep, lambda docs: self.driver.post(ep, docs=docs))
        if stream_endpoints:
            for ep in stream_endpoints:
                setattr(self, ep, lambda: self.driver.stream(ep))


    async def post(self, on: str, docs: Optional[DocArray] = None) -> Optional[DocArray]:
        '''Invokes an endpoint specified by 'on'.

        The reason why we use getattr every time this method is called is that
        an executor can hold both endpoints itself (accessed by self) and
        endpoints via a gateway using a client.
        '''
        try:
            func = getattr(self, on)
            return await func(docs)
        except AttributeError:
            # fallback to the client
            return await self.driver.post(on, docs)
        

    
    async def stream(self, on: str) -> Stream: raise NotImplementedError


    def __enter__(self):
        return self
    

    def __exit__(self):
        self.driver.stop()


class Flow:

    def __init__(self,
                 name: Optional[str] = None,
                 driver: Optional['Driver'] = None):
        '''Create a flow.'''
        self.name = name
        self.driver = driver
        self.nodes = {}
        self.edges = {}


    def add(self, 
            use: Union[Executor, str],
            *,
            on: Optional[str] = None,
            id: Optional[str] = None,
            needs: Optional[Iterable[str]] = None,
            reduce: bool = False) -> 'Flow':
        '''Adds an executor to the flow with optionally specified dependencies.
        
        This method takes an executor or a URI to it and inserts it into a DAG
        aka. Directed Acyclic Graph, taking 'needs' as links coming from those
        that must finish executing before the one being added. NOTE that 'on'
        must be specified if 'use' is an instance of Executor to tell the DAG 
        which endpoint to use.
        '''
        if isinstance(use, Executor):
            if on is None:
                raise ValueError(f"'on' must be specified when 'use' is an instance of Execcutor")
            id = '/'.join(use.name, on)
        elif isinstance(use, str):
            id = use
            url = urlparse(use)
            name, endpoint = _parse_path(url.path[1:])
            use = Executor(name=name,
                           gateway=url.netloc,
                           driver=self.driver,
                           post_endpoints=(endpoint,))
        else:
            raise TypeError(f"'use' can only be an instance of either Executor or str")
        
        self.nodes[id] = use
        self.edges[id] = needs
        
        if reduce:
            raise NotImplementedError


    async def post(self, docs: Optional[DocArray] = None) -> Optional[DocArray]:
        '''Fires the flow of executors and wait until the last executor finishes.
        '''
        raise NotImplementedError



def _parse_path(path: str) -> Tuple[str, str]:
    i = path.find('/')
    return path[:i], path[i+1:]


if __name__ == '__main__':
    from dataclasses import dataclass

    class MyExecutor(Executor):
        @post
        def echo(self, docs: DocArray) -> Optional[DocArray]:
            return docs


    @dataclass
    class YourDoc:
        text: Text


    @dataclass
    class MyDoc:
        image: Image
        text: Text
        your: YourDoc


    d = MyDoc(
        text=Text(text='Aa'), 
        image=Image(ref='a.jpg'),
        your=YourDoc(text=Text(text='Bb')),
    )
    
    
    s = MyExecutor(name='my_Executor', post_endpoints=['ping'])
    