__version__ = '0.0.0'

from typing import (
    TypeVar, 
    ForwardRef, 
    Optional,
    Union,
    Tuple,
    List,
    Any,
    Type,
    Iterable,
    BinaryIO,
    Callable,
)
from abc import ABC, abstractmethod
from urllib.parse import urlparse
from inspect import getfullargspec, iscoroutinefunction
from functools import wraps
from uuid import UUID, uuid1

from pydantic import BaseModel, Field


PILImage = TypeVar('PILImage', bound=ForwardRef('PIL.Image'))
Tensor = TypeVar('Tensor', bound=ForwardRef('numpy.ndarray'))


class Driver(ABC):

    def __init__(self,
                 *,
                 host: str = '127.0.0.1',
                 port: int = 8080,
                 keyfile: Optional[str] = None,
                 certfile: Optional[str] = None):
        ''''Create a driver instance.'''
        self.host = host
        self.port = port
        self.keyfile = keyfile
        self.certfile = certfile

    
    @abstractmethod
    def add(self, use: 'Executor', id: Optional[str] = None):
        '''Adds an executor into the driver to subscribe on doc requests.'''
        raise NotImplementedError


    @abstractmethod
    def remove(self, id: str):
        '''Removes an executor specified by 'id' from the driver.'''
        raise NotImplementedError


    @abstractmethod
    async def post(self, path: str, doc: 'Doc', res_type: Type['Doc']) -> Optional['Doc']:
        '''Posts one or more docs to the endpoint speicified by 'path'.'''
        raise NotImplementedError


    @abstractmethod
    async def stream(self, on: str) -> 'Stream':
        '''Creates a stream used to send/receive a doc to/from an endpoint'''
        raise NotImplementedError


    @abstractmethod
    def start(self):
        '''Starts up the driver.'''
        raise NotImplementedError


    @abstractmethod
    def stop(self, timeout: int = 300):
        '''Stops the driver in 'timeout' milliseconds, default to 300ms.'''
        raise NotImplementedError
    


class NoopDriver(Driver):

    def add(self, use: 'Executor', id: Optional[str] = None):
        return super().add(use, id)
    
    def remove(self, id: str):
        return super().remove(id)

    async def post(self, on: str, doc: 'Doc') -> Optional['Doc']:
        return await super().post(on, doc)
    
    async def stream(self, on: str) -> 'Stream':
        return await super().stream(on)
    
    def start(self):
        return super().start()
    
    def stop(self, timeout: int = 300):
        return super().stop(timeout)



class Store(ABC):

    def __init__(self,
                 gateway: str):
        '''Creates a storage instance.'''
        self.gateway = gateway


    @abstractmethod
    async def put(self, reader: BinaryIO):
        raise NotImplementedError
    

    @abstractmethod
    async def get(self, path: str) -> BinaryIO:
        raise NotImplementedError
    


class ComboDoc(BaseModel): ...


class Doc(BaseModel):
    '''A class with some abstract methods to represent model input or output.'''

    id: UUID = Field(default_factory=uuid1)
    ref: Optional[str]
    sig: Optional[str]
    value: Optional[str]
    
    
    @abstractmethod
    def tensor(self) -> Tensor:
        '''Returns a tensor representation of the doc.'''
        raise NotImplementedError


class Text(Doc):
    '''A class derived from Doc for representing text.'''

    def tensor(self) -> Tensor:
        # TODO:
        raise NotImplementedError
        


class Image(Doc):
    '''A class derived from Doc for representing an image.'''

    def tensor(self) -> Tensor:
        # TODO: 
        raise NotImplementedError


    def show(self) -> None:
        # TODO:
        raise NotImplementedError


class PostWrapperAsync:

    def __init__(self,
                 func: Callable[['Executor', 'Doc'], Optional['Doc']],
                 on: Optional[str] = None,
                 batch_size: Optional[int] = None,
                 timeout: int = 300):
        '''Creates a PostWrapper instance.'''

        self.func = func
        self.on = on or func.__name__
        self.batch_size = batch_size
        self.timeout = timeout

        if not iscoroutinefunction(func):
            @wraps(func)
            async def async_func(self: 'Executor', doc: 'Doc') -> Optional['Doc']:
                return func(self, doc)
            self.func = async_func

        self.spec = getfullargspec(self.func)
        if 'doc' not in self.spec.annotations:
            raise TypeError(f"The argument of handler '{self.on}' must be named as 'doc'")


    async def __call__(self, exe: 'Executor', doc: Doc) -> Optional['Doc']:
        # TODO: batching
        return await self.func(exe, doc)
    

class StreamWrapper:

    def __init__(self,
                 func: Callable[['Stream'], None],
                 on: Optional[str] = None):
        '''Creates a StreamWrapper instance.'''
        
        self.func = func
        self.on = on
        self.spec = getfullargspec(func)



def post(func: Optional[Callable[['Executor', 'Doc'], Optional['Doc']]] = None, 
         batch_size: Optional[int] = None,
         timeout: Optional[int] = None,
         on: Optional[str] = None):
    '''Returns a executor's method as a post endpoint handler.

    Using this function as a decorator is recommanded.
    '''
    def wrap(func):
        return PostWrapperAsync(func, on, batch_size, timeout)
    
    if func is None:
        # we are being used as @on()
        return wrap
    # we are being used as @on
    return wrap(func)


def stream(func: Optional[Callable[['Stream'], None]],
           on: Optional[str] = None):
    '''Returns a Executor method as a stream handler.'''
    def wrap(func):
        return StreamWrapper(func, on)
    
    if func is None:
        # we are being used as @on()
        return wrap
    # we are being used as @on
    return wrap(func)



def _attrs(obj: object, cls: type) -> List[Any]:
    '''Returns a list containing all attributes of type 'cls' in 'obj'.'''
    attrs = []
    for name in obj.__dir__():
        attr = getattr(obj, name)
        if isinstance(attr, cls):
            attrs.append(attr)
    return attrs


class Stream: ...

class Executor:

    def __init__(self,
                 *,
                 name: Optional[str] = None,
                 driver: Optional['Driver'] = None,
                 store: Optional['Store'] = None,
                 post_endpoints: Optional[Iterable[str]] = None,
                 stream_endpoints: Optional[Iterable[str]] = None,):
        '''Instantiate an executor.'''
        self.name = name or self.__class__.__name__
        self.driver = driver
        self.store = store

        if self.driver is None:
            self.driver = NoopDriver()

        self.driver.add(self)

        # Inject endpoints dynamically so that they can be accessed by self.post
        # using getattr.
        if post_endpoints:
            for on in post_endpoints:
                path = f'/{self.name}/{on}'
                setattr(self, on, lambda doc, res_type: self.driver.post(path, doc, res_type))
        if stream_endpoints:
            for on in stream_endpoints:
                path = f'/{self.name}/{on}'
                setattr(self, on, lambda: self.driver.stream(path))


    async def post(self, *,
                   on: str, 
                   doc: Doc,
                   res_type: Type[Doc]) -> Optional[Doc]:
        '''Invokes an endpoint specified by 'on'.

        The reason why we use getattr every time this method is called is that
        an executor can hold both endpoints itself (accessed by self) and
        endpoints via a gateway using a client.
        '''
        try:
            func = getattr(self, on)
            return await func(doc, res_type)
        except AttributeError:
            # fallback to the client
            path = f'/{self.name}/{on}'
            return await self.driver.post(path, doc, res_type)
        

    
    async def stream(self, on: str) -> Stream: raise NotImplementedError


    def serve(self):
        '''Starts serving the executor.'''
        self.driver.start()



    def post_handlers(self) -> List[PostWrapperAsync]:
        return _attrs(self, PostWrapperAsync)
    

    def stream_handlers(self) -> List[StreamWrapper]:
        return _attrs(self, StreamWrapper)


    def __enter__(self):
        return self
    

    def __exit__(self, *args):
        self.driver.stop()


    async def __aenter__(self):
        return self
    

    async def __aexit__(self, *args):
        self.driver.stop()



class Flow:

    def __init__(self,
                 name: Optional[str] = None,
                 driver: Optional['Driver'] = None,
                 store: Optional['Store'] = None):
        '''Create a flow.'''
        self.name = name
        self.driver = driver
        self.store = store
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
                           store=self.store,
                           post_endpoints=(endpoint,))
        else:
            raise TypeError(f"'use' can only be an instance of either Executor or str")
        
        self.nodes[id] = use
        self.edges[id] = needs
        
        if reduce:
            raise NotImplementedError


    async def post(self, doc: Doc) -> Optional[Doc]:
        '''Fires the flow of executors and wait until the last executor finishes.'''
        raise NotImplementedError



def _parse_path(path: str) -> Tuple[str, str]:
    i = path.find('/')
    return path[:i], path[i+1:]
